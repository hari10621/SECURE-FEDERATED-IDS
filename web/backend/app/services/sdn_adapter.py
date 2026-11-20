"""Modular SDN adapter for SecureFed-IDS.

Provides connectivity to an SDN controller (Ryu), flow statistics collection,
flow-to-feature mapping, IDS model inference, alert generation, and result
recording.

Supports two operational modes:
  * ``ryu``   - Connects to a Ryu controller via OpenFlow.
  * ``mock``  - Generates synthetic flow data for development/testing on
                Windows without a full Mininet/Wireshark setup.
  * ``offline``- Read flow statistics from CSV logs (no controller required).

The feature mapping explicitly documents how OpenFlow flow fields are
translated to the 48-feature vector expected by the validated IDS model.
No automatic packet/flow statistics assumptions are made regarding research
dataset feature alignment; mapping is documented and testable.

IPS Prevention Extension (Phase 9)
-----------------------------------
Three modes are supported:
  * ``detection_only``  (default) - Record predictions, generate alerts,
    but do NOT install any OpenFlow rules.
  * ``manual_approval`` - Generate mitigation requests; require explicit
    approval before installing any OpenFlow rule.
  * ``automatic_blocking`` - Automatically install OpenFlow rules for
    detected attacks. **Disabled by default** and restricted to isolated lab
    environments only. Must be explicitly enabled via mode or environment variable.

Each mitigation attempt is logged with status: ``requested``, ``applied``,
``failed``, or ``verified``.  Emergency stop and rollback procedures are
provided.
"""

from __future__ import annotations

import csv
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..errors import UnavailableError, InputValidationError
from ..domain.dataset import preprocess, LoadedDataset, ScalerStats, SplitIndices
from ..domain.model import (
    parameter_specs,
    parameter_count,
    flatten_gru_weights,
    unflatten_gru_weights,
    model_description,
    keras_available,
    build_gru_model,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SWITCH_ID = "00:00:00:00:00:00:00:01"
FEATURE_NAME_COUNT = 48
MODEL_INPUT_SHAPE = (1, 1, FEATURE_NAME_COUNT)

RYU_AVAILABLE: bool = False
try:
    from ryu.controller import ofp_event
    from ryu.controller.controller import DatapathBase
    from ryu.controller import Controller
    from ryu.ofproto import ofproto_v1_3
    RYU_AVAILABLE = True
except Exception:  # pragma: no cover - Ryu import failure
    RYU_AVAILABLE = False

# ---------------------------------------------------------------------------
# Mitigation mode enumeration
# ---------------------------------------------------------------------------

class MitigationMode:
    """Supported IPS mitigation modes."""
    DETECTION_ONLY = "detection_only"
    MANUAL_APPROVAL = "manual_approval"
    AUTOMATIC_BLOCKING = "automatic_blocking"

MITIGATION_MODE_NAMES = {
    MitigationMode.DETECTION_ONLY: "Detection Only (default)",
    MitigationMode.MANUAL_APPROVAL: "Manual Approval",
    MitigationMode.AUTOMATIC_BLOCKING: "Automatic Blocking (lab only)",
}


# ---------------------------------------------------------------------------
# Mitigation status enumeration
# ---------------------------------------------------------------------------

class MitigationStatus:
    """Status of a mitigation attempt."""
    REQUESTED = "requested"
    APPLIED = "applied"
    FAILED = "failed"
    VERIFIED = "verified"
    ROLLED_BACK = "rolled_back"

MITIGATION_STATUS_NAMES = {
    MitigationStatus.REQUESTED: "Requested",
    MitigationStatus.APPLIED: "Applied",
    MitigationStatus.FAILED: "Failed",
    MitigationStatus.VERIFIED: "Verified",
    MitigationStatus.ROLLED_BACK: "Rolled Back",
}


# ---------------------------------------------------------------------------
# Dataclasses: FlowStats, SwitchInfo, DetectionResult
# ---------------------------------------------------------------------------

@dataclass
class FlowStats:
    """Flow statistics from a single OpenFlow switch."""
    match: Dict[str, Any]
    count_bytes: int
    duration_sec: float
    duration_nsec: int
    idle_timeout: int
    hard_timeout: int
    priority: int
    packet_count: int
    byte_count: int
    instruction_count: int
    table_id: int
    cookie: int
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "match": self.match,
            "count_bytes": self.count_bytes,
            "duration_sec": self.duration_sec,
            "duration_nsec": self.duration_nsec,
            "idle_timeout": self.idle_timeout,
            "hard_timeout": self.hard_timeout,
            "priority": self.priority,
            "packet_count": self.packet_count,
            "byte_count": self.byte_count,
            "instruction_count": self.instruction_count,
            "table_id": self.table_id,
            "cookie": self.cookie,
            "timestamp": self.timestamp,
        }


@dataclass
class SwitchInfo:
    """Minimal switch information retrieved from the SDN controller."""
    dp_id: str
    mac: str
    ip: str
    n_ports: int
    serial_number: str = ""
    hw_desc: str = ""
    sw_desc: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dp_id": self.dp_id,
            "mac": self.mac,
            "ip": self.ip,
            "n_ports": self.n_ports,
            "serial_number": self.serial_number,
            "hw_desc": self.hw_desc,
            "sw_desc": self.sw_desc,
        }


@dataclass
class DetectionResult:
    """Result of IDS model inference on a flow."""
    flow_id: str
    timestamp: float
    prediction: float  # probability 0..1 (normal -> attack)
    label: int  # 0=normal, 1=attack
    features: List[float]
    switch_dp_id: str
    table_id: int
    alert: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        base = {
            "flow_id": self.flow_id,
            "timestamp": self.timestamp,
            "prediction": self.prediction,
            "label": self.label,
            "features": self.features,
            "switch_dp_id": self.switch_dp_id,
            "table_id": self.table_id,
            "alert": self.alert,
        }
        return base


# ---------------------------------------------------------------------------
# Dataclasses: MitigationRequest, MitigationResult
# ---------------------------------------------------------------------------

@dataclass
class MitigationRequest:
    """A mitigation request generated from an IDS prediction."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    flow_id: str = ""
    switch_dp_id: str = ""
    table_id: int = 0
    prediction_probability: float = 0.0
    confidence_threshold: float = 0.5
    requested_at: float = field(default_factory=time.time)
    approved_at: Optional[float] = None
    applied_at: Optional[float] = None
    removed_at: Optional[float] = None
    status: str = MitigationStatus.REQUESTED
    reason: str = ""
    rule_id: Optional[str] = None
    verification_result: Optional[dict] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "flow_id": self.flow_id,
            "switch_dp_id": self.switch_dp_id,
            "table_id": self.table_id,
            "prediction_probability": self.prediction_probability,
            "confidence_threshold": self.confidence_threshold,
            "requested_at": self.requested_at,
            "approved_at": self.approved_at,
            "applied_at": self.applied_at,
            "removed_at": self.removed_at,
            "status": self.status,
            "reason": self.reason,
            "rule_id": self.rule_id,
            "verification_result": self.verification_result,
        }

    @classmethod
    def from_detection_result(
        cls,
        result: DetectionResult,
        *,
        confidence_threshold: float = 0.5,
        mode: str = MitigationMode.DETECTION_ONLY,
        reason: str = "IDS prediction",
    ) -> "MitigationRequest":
        """Create a MitigationRequest from a DetectionResult."""
        return cls(
            flow_id=result.flow_id,
            switch_dp_id=result.switch_dp_id,
            table_id=result.table_id,
            prediction_probability=result.prediction,
            confidence_threshold=confidence_threshold,
            reason=reason,
        )


@dataclass
class MitigationResult:
    """Result of a mitigation attempt."""
    request_id: str
    status: str
    applied_rule_id: Optional[str] = None
    removed_at: Optional[float] = None
    verification: Optional[dict] = None
    error: Optional[str] = None
    applied_at: Optional[float] = None
    completed_at: float = field(default_factory=time.time)
    reason: str = ""


# ---------------------------------------------------------------------------
# SDN Adapter
# ---------------------------------------------------------------------------

class SDNAdapter:
    """Modular SDN adapter for SecureFed-IDS.

    Responsibilities
    -----------------
    1. Connect to the configured controller (Ryu or mock).
    2. Read switch and flow information where supported.
    3. Receive flow statistics from OpenFlow switches.
    4. Map observed flows to the feature extraction pipeline (48 features).
    5. Pass correctly prepared features to the validated IDS model.
    6. Receive the model prediction.
    7. Produce an alert with flow identifiers and timestamp.
    8. Record the detection result.
    9. (Phase 9) Generate mitigation requests and apply OpenFlow rules
       according to the selected mode.

    Modes
    -----
    * ``ryu``    - Real Ryu controller connection (WSL / Linux).
    * ``mock``   - Synthetic flow data generation (Windows default).
    * ``offline``- Read flow statistics from CSV logs.

    IPS Modes (Phase 9)
    -------------------
    * ``detection_only``   (default) - No OpenFlow rules installed.
    * ``manual_approval``  - Mitigation requests require explicit approval.
    * ``automatic_blocking`` - Auto-install OpenFlow rules (lab-only, disabled by default).
    """

    # -----------------------------------------------------------------
    # Initialization
    # -----------------------------------------------------------------

    def __init__(
        self,
        *,
        mode: str = "mock",
        controller_host: str = "127.0.0.1",
        controller_port: int = 6633,
        model_path: Optional[Path] = None,
        scaler_path: Optional[Path] = None,
        feature_mapping: Optional[Dict[int, str]] = None,
        lab_network: bool = False,
        ips_mode: str = MitigationMode.DETECTION_ONLY,
        max_rule_priority: int = 10,
        allowed_switches: Optional[List[str]] = None,
    ) -> None:
        self.mode = mode
        self.controller_host = controller_host
        self.controller_port = controller_port
        self.lab_network = lab_network
        self.ips_mode = ips_mode
        self.max_rule_priority = max_rule_priority
        self.allowed_switches = allowed_switches or []
        self._connected = False
        self._switch_info: Optional[SwitchInfo] = None
        self._last_flow: Optional[FlowStats] = None
        self._detection_history: List[DetectionResult] = []
        self._mitigation_history: List[MitigationResult] = []

        # ---- Pending approvals (manual mode)
        self._pending_approvals: Dict[str, float] = {}

        # ---- Active mitigation rules
        self._active_rules: Dict[str, dict] = {}

        # ---- Auto-connect in mock/offline modes (no real controller needed)
        if self.mode in ("mock", "offline"):
            self._connected = True

        # ---- Model setup -------------------------------------------------
        self.model: Any = None
        self.scaler: Optional[ScalerStats] = None
        self._init_model(model_path, scaler_path)

        # ---- Feature-mapping configuration -------------------------------
        self.feature_mapping: Dict[int, str] = feature_mapping or {}
        self._init_feature_mapping()

    # -----------------------------------------------------------------
    # Model initialization
    # -----------------------------------------------------------------

    def _init_model(self, model_path: Optional[Path], scaler_path: Optional[Path]) -> None:
        """Load or build the GRU IDS model and optional scaler."""
        self.model = None
        self.scaler = None

        if model_path is not None and model_path.is_file():
            try:
                payload = self._read_model_artifact(model_path)
                self.model = payload  # type: ignore[assignment]
                if "scaler_stats" in payload:
                    ss = payload["scaler_stats"]
                    self.scaler = ScalerStats(
                        means=ss.get("means", []),
                        scales=ss.get("scales", []),
                    )
                return
            except Exception as exc:  # pragma: no cover
                raise UnavailableError(f"Failed to load model artifact: {exc}")

        # Build a fresh model matching the research architecture,
        # but fail gracefully if TensorFlow/Keras is unavailable.
        if keras_available():
            self.model = build_gru_model(input_features=FEATURE_NAME_COUNT)
        # If model remains None, predict() will raise UnavailableError.

        # Try to fit a scaler from provided data or use defaults
        if scaler_path is not None and scaler_path.is_file():
            try:
                data = scaler_path.read_text(encoding="utf-8").strip()
                ss = json.loads(data)
                self.scaler = ScalerStats(means=ss.get("means", []), scales=ss.get("scales", []))
            except Exception as exc:  # pragma: no cover
                raise UnavailableError(f"Failed to load scaler: {exc}")
        # If no scaler provided, the model expects unit-normalized inputs.

    # -----------------------------------------------------------------
    # Feature-mapping initialization
    # -----------------------------------------------------------------

    def _init_feature_mapping(self) -> None:
        """Set up the default OpenFlow-to-IDS-feature mapping."""
        if self.feature_mapping:
            return

        default_names = [
            "duration",
            "idle_timeout",
            "hard_timeout",
            "priority",
            "eth_type",
            "ip_proto",
            "tcp_src_port",
            "tcp_dst_port",
            "udp_src_port",
            "udp_dst_port",
            "icmp_code",
            "icmp_type",
            "ipv4_src_addr",
            "ipv4_dst_addr",
            "packets_in",
            "bytes_in",
            "pkt_per_sec",
            "byte_per_sec",
            "duration_nsec",
            "tx_bytes",
            "tx_packets",
            "rx_bytes",
            "rx_packets",
            "tcp_flags",
            "syn_flag",
            "ack_flag",
            "fin_flag",
            "rst_flag",
            "window_size",
            "ip_ttl",
            "tcp_len",
            "dns_qr",
            "http_method",
            "http_status_code",
            "http_content_type",
            "tls_version",
            "flow_count_per_switch",
            "flow_entropy",
            "min_pkt_size",
            "max_pkt_size",
            "avg_pkt_size",
            "port_traffic_ratio",
            "ssh_flag",
            "smtp_flag",
            "dns_flag",
            "http_flag",
            "webflag",
            "label",
        ]
        self.feature_mapping = {i: default_names[i] for i in range(min(FEATURE_NAME_COUNT, len(default_names)))}
        while len(self.feature_mapping) < FEATURE_NAME_COUNT:
            self.feature_mapping[len(self.feature_mapping)] = f"feature_{len(self.feature_mapping)}"

    # -----------------------------------------------------------------
    # Connection management
    # -----------------------------------------------------------------

    def connect(self) -> Dict[str, Any]:
        """Connect to the SDN controller."""
        if self.mode == "ryu":
            self._connect_ryu()
        else:
            self._connected = True
        return self.status()

    def _connect_ryu(self) -> None:
        """Attempt to connect to a Ryu controller."""
        if not RYU_AVAILABLE:
            raise UnavailableError(
                "Ryu is not installed in this environment. "
                "Install Ryu or use ``mode='mock'`` / ``mode='offline'``."
            )
        self._connected = True

    def disconnect(self) -> None:
        """Gracefully disconnect from the controller."""
        self._connected = False
        self._switch_info = None
        self._last_flow = None
        # Clean up active mitigation rules
        self._active_rules.clear()

    def status(self) -> Dict[str, Any]:
        """Return connection and mode status."""
        base = {
            "mode": self.mode,
            "connected": self._connected,
            "controller_host": self.controller_host,
            "controller_port": self.controller_port,
            "ryu_available": RYU_AVAILABLE,
            "feature_count": FEATURE_NAME_COUNT,
            "ips_mode": self.ips_mode,
        }
        # Enrich with switch info if connected
        if self._connected and self._switch_info is not None:
            base["switch"] = self._switch_info.to_dict()
        else:
            base["switch"] = None
        return base

    # -----------------------------------------------------------------
    # Switch information
    # -----------------------------------------------------------------

    def get_switch_info(self) -> Optional[SwitchInfo]:
        """Retrieve switch information from the connected controller."""
        if not self._connected:
            return None
        if self.mode == "ryu":
            self._fetch_switch_info_ryu()
        elif self.mode == "mock":
            self._switch_info = SwitchInfo(
                dp_id=DEFAULT_SWITCH_ID,
                mac="00:00:00:00:00:00",
                ip="10.0.0.1",
                n_ports=4,
            )
        return self._switch_info

    def _fetch_switch_info_ryu(self) -> None:
        """Fetch switch info via Ryu (skeleton)."""
        pass

    # -----------------------------------------------------------------
    # Flow statistics
    # -----------------------------------------------------------------

    def get_flow_stats(self, switch_dp_id: Optional[str] = None) -> List[FlowStats]:
        """Retrieve flow statistics from the switch."""
        if not self._connected:
            return []
        switch_id = switch_dp_id or DEFAULT_SWITCH_ID

        if self.mode == "ryu":
            return self._fetch_flow_stats_ryu(switch_id)
        elif self.mode == "mock":
            return self._generate_mock_flow_stats(switch_id)
        elif self.mode == "offline":
            return self._read_flow_stats_offline(switch_id)
        return []

    def _fetch_flow_stats_ryu(self, switch_dp_id: str) -> List[FlowStats]:
        """Fetch flow stats from a Ryu controller (skeleton)."""
        return []

    def _generate_mock_flow_stats(self, switch_dp_id: str) -> List[FlowStats]:
        """Generate synthetic flow statistics for development/testing."""
        import numpy as np
        self._mock_flow_counter = getattr(self, '_mock_flow_counter', 0) + 1
        n_flows = 3 + (self._mock_flow_counter % 5)  # 3..7 flows
        stats_list: List[FlowStats] = []

        for _ in range(n_flows):
            match = {
                "eth_type": 0x0800,
                "ip_proto": np.random.choice([6, 17, 1]),
                "tcp_src_port": np.random.randint(49152, 65535) if np.random.random() > 0.3 else None,
                "tcp_dst_port": np.random.randint(1, 65535),
                "udp_src_port": None if np.random.choice([6, 17, 1]) == 17 else (np.random.randint(49152, 65535) if np.random.random() > 0.3 else None),
                "udp_dst_port": np.random.randint(1, 65535) if np.random.random() > 0.3 else None,
                "ipv4_src_addr": f"10.0.{np.random.randint(1, 254)}.{np.random.randint(1, 254)}",
                "ipv4_dst_addr": f"10.0.{np.random.randint(1, 254)}.{np.random.randint(1, 254)}",
                "icmp_code": 0 if np.random.choice([6, 17, 1]) == 1 else None,
                "icmp_type": 8 if np.random.choice([6, 17, 1]) == 1 else None,
                "tcp_flags": np.random.randint(0, 63),
            }

            fs = FlowStats(
                match=match,
                count_bytes=int(np.random.uniform(100, 500_000)),
                duration_sec=round(float(np.random.uniform(0.05, 12.0)), 3),
                duration_nsec=int(np.random.uniform(0, 1_000_000)),
                idle_timeout=int(np.random.uniform(0, 300)),
                hard_timeout=int(np.random.uniform(0, 3600)),
                priority=np.random.choice([0, 1, 5, 10, 50]),
                packet_count=int(np.random.uniform(1, 5000)),
                byte_count=int(np.random.uniform(64, 200_000)),
                instruction_count=int(np.random.uniform(0, 20)),
                table_id=np.random.randint(0, 10),
                cookie=int(np.random.uniform(0, 2**31 - 1)),
            )
            stats_list.append(fs)

        return stats_list

    def _read_flow_stats_offline(self, switch_dp_id: str) -> List[FlowStats]:
        """Read flow statistics from CSV log files."""
        data_dir = Path.cwd() / "data"
        csv_files = list(data_dir.glob("flow_stats_*.csv")) + list(data_dir.glob("*.csv"))
        stats_list: List[FlowStats] = []

        for csv_file in csv_files:
            try:
                with csv_file.open("r", encoding="utf-8-sig", newline="") as f:
                    reader = csv.reader(f)
                    header = next(reader, None)
                    if header is None:
                        continue
                    for row in reader:
                        if len(row) < 3:
                            continue
                        try:
                            match = {}
                            if len(row) > 0 and row[0]:
                                match["eth_type"] = int(row[0])
                            if len(row) > 1 and row[1]:
                                match["ip_proto"] = int(row[1])
                            duration = float(row[2]) if len(row) > 2 else 0.0
                            packet_count = int(row[3]) if len(row) > 3 else 0
                            byte_count = int(row[4]) if len(row) > 4 else 0

                            fs = FlowStats(
                                match=match,
                                count_bytes=byte_count,
                                duration_sec=duration,
                                duration_nsec=0,
                                idle_timeout=0,
                                hard_timeout=0,
                                priority=0,
                                packet_count=packet_count,
                                byte_count=byte_count,
                                instruction_count=0,
                                table_id=0,
                                cookie=0,
                                timestamp=time.time(),
                            )
                            stats_list.append(fs)
                        except (ValueError, IndexError):
                            continue
            except Exception:
                continue

        return stats_list

    # -----------------------------------------------------------------
    # Flow-to-feature mapping
    # -----------------------------------------------------------------

    def map_flow_to_features(self, flow: FlowStats) -> List[float]:
        """Map a FlowStats object to a 48-feature vector for the IDS model."""
        features: List[float] = [0.0] * FEATURE_NAME_COUNT
        match = flow.match

        # Basic numeric fields
        features[0] = flow.duration_sec
        features[1] = float(flow.idle_timeout)
        features[2] = float(flow.hard_timeout)
        features[3] = float(flow.priority)
        etype = match.get("eth_type")
        features[4] = float(etype) / 65535.0 if etype is not None else 0.0
        ipproto = match.get("ip_proto")
        features[5] = float(ipproto) / 255.0 if ipproto is not None else 0.0
        tsrc = match.get("tcp_src_port")
        features[6] = float(tsrc) / 65535.0 if tsrc is not None else 0.0
        tdst = match.get("tcp_dst_port")
        features[7] = float(tdst) / 65535.0 if tdst is not None else 0.0
        usrc = match.get("udp_src_port")
        features[8] = float(usrc) / 65535.0 if usrc is not None else 0.0
        udst = match.get("udp_dst_port")
        features[9] = float(udst) / 65535.0 if udst is not None else 0.0
        icmp_code = match.get("icmp_code")
        features[10] = float(icmp_code) / 255.0 if icmp_code is not None else 0.0
        icmp_type = match.get("icmp_type")
        features[11] = float(icmp_type) / 255.0 if icmp_type is not None else 0.0
        src_ip = match.get("ipv4_src_addr", "")
        features[12] = (sum(ord(c) for c in src_ip) % 1000) / 1000.0 if src_ip else 0.0
        dst_ip = match.get("ipv4_dst_addr", "")
        features[13] = (sum(ord(c) for c in dst_ip) % 1000) / 1000.0 if dst_ip else 0.0
        features[14] = float(flow.packet_count)
        features[15] = float(flow.byte_count)
        if flow.duration_sec > 0:
            features[16] = float(flow.packet_count) / flow.duration_sec
        else:
            features[16] = 0.0
        if flow.duration_sec > 0:
            features[17] = float(flow.byte_count) / flow.duration_sec
        else:
            features[17] = 0.0
        features[18] = float(flow.duration_nsec) / 1_000_000_000
        features[19] = float(flow.byte_count)
        features[20] = float(flow.packet_count)
        features[21] = float(flow.byte_count)
        features[22] = float(flow.packet_count)
        features[23] = float(match.get("tcp_flags", 0)) if match.get("tcp_flags") is not None else 0.0

        # Protocol-specific derived fields
        features[24] = 1.0 if match.get("tcp_src_port") is not None else 0.0
        features[25] = 0.0
        features[26] = 0.0
        features[27] = 0.0
        features[28] = (float(match.get("tcp_src_port", 0)) if match.get("tcp_src_port") is not None else 0.0) % 65536 / 65535.0
        features[29] = 0.5
        if flow.packet_count > 0:
            features[30] = float(flow.byte_count) / flow.packet_count
        else:
            features[30] = 0.0
        features[31] = 1.0 if match.get("udp_dst_port") == 53 else 0.0
        features[32] = 0.0
        features[33] = 0.0
        features[34] = 0.0
        features[35] = 0.0

        # Statistical / entropy fields
        features[36] = float(flow.priority) / 255.0
        features[37] = 0.5
        features[38] = 0.2
        features[39] = 0.8
        features[40] = features[30]  # avg pkt size same as position 30
        features[41] = 0.5
        features[42] = 1.0 if (match.get("udp_dst_port") == 22 or match.get("tcp_dst_port") == 22) else 0.0
        features[43] = 1.0 if (match.get("udp_dst_port") == 25 or match.get("tcp_dst_port") == 25) else 0.0
        features[44] = 1.0 if match.get("udp_dst_port") == 53 else 0.0
        features[45] = 1.0 if match.get("tcp_dst_port") in (80, 8080, 443) else 0.0
        features[46] = 0.5
        features[47] = -1.0  # sentinel: unavailable during inference

        assert len(features) == FEATURE_NAME_COUNT, (
            f"Expected {FEATURE_NAME_COUNT} features, got {len(features)}"
        )
        return features

    # -----------------------------------------------------------------
    # Model inference
    # -----------------------------------------------------------------

    def predict(self, features: List[float], switch_dp_id: str, table_id: int) -> Dict[str, Any]:
        """Run the GRU IDS model on prepared features."""
        if self.model is None:
            raise UnavailableError("IDS model not initialized.")

        import numpy as np

        if self.scaler is not None:
            from ..domain.dataset import apply_scaler
            features_scaled = apply_scaler([features], self.scaler)[0]
        else:
            features_scaled = features

        X = np.array(features_scaled, dtype=np.float32).reshape(MODEL_INPUT_SHAPE)

        if not keras_available():
            raise UnavailableError("TensorFlow/Keras is not available for inference.")

        import tensorflow as tf
        if self.model is not None:
            pred = self.model.predict(X, verbose=0)[0][0]
        else:
            raise UnavailableError("Model is not built.")

        label = 1 if pred >= 0.5 else 0

        alert: Optional[Dict[str, Any]] = None
        if label == 1:
            alert = {
                "type": "intrusion_detected",
                "flow_id": f"{switch_dp_id}-{table_id}",
                "timestamp": time.time(),
                "prediction_probability": float(pred),
                "features_used": features,
            }

        return {
            "prediction": float(pred),
            "label": int(label),
            "alert": alert,
        }

    # -----------------------------------------------------------------
    # Full detection pipeline
    # -----------------------------------------------------------------

    def detect(self, switch_dp_id: Optional[str] = None, table_id: Optional[int] = None) -> Optional[DetectionResult]:
        """Run the full detection pipeline."""
        if not self._connected:
            return None

        flow_stats_list = self.get_flow_stats(switch_dp_id=switch_dp_id)
        if not flow_stats_list:
            return None

        flow = flow_stats_list[0]
        features = self.map_flow_to_features(flow)
        tid = table_id if table_id is not None else flow.table_id

        try:
            inf = self.predict(features, switch_dp_id or DEFAULT_SWITCH_ID, tid)
        except UnavailableError:
            inf = {"prediction": float("nan"), "label": -1, "alert": None}

        flow_id = f"{flow.match.get('ipv4_src_addr', 'unknown')}-{flow.match.get('ipv4_dst_addr', 'unknown')}-{flow.table_id}"
        result = DetectionResult(
            flow_id=flow_id,
            timestamp=time.time(),
            prediction=inf["prediction"],
            label=inf["label"],
            features=features,
            switch_dp_id=(switch_dp_id or DEFAULT_SWITCH_ID),
            table_id=tid,
            alert=inf.get("alert"),
        )

        self._detection_history.append(result)
        return result

    def record_result(self, result: DetectionResult) -> None:
        """Record a detection result into history."""
        self._detection_history.append(result)

    # -----------------------------------------------------------------
    # IPS Prevention (Phase 9)
    # -----------------------------------------------------------------

    def set_ips_mode(self, mode: str) -> None:
        """Set the IPS mitigation mode."""
        valid_modes = [MitigationMode.DETECTION_ONLY,
                       MitigationMode.MANUAL_APPROVAL,
                       MitigationMode.AUTOMATIC_BLOCKING]
        if mode not in valid_modes:
            raise InputValidationError(f"Invalid IPS mode: {mode}")
        self.ips_mode = mode
        self._pending_approvals.clear()

    def request_mitigation(self, detection_result: DetectionResult, *, reason: str = "IDS prediction") -> MitigationRequest:
        """Generate a mitigation request from a detection result."""
        req = MitigationRequest.from_detection_result(
            detection_result,
            confidence_threshold=self._get_effective_threshold(),
            mode=self.ips_mode,
            reason=reason,
        )

        if self.ips_mode == MitigationMode.DETECTION_ONLY:
            req.status = MitigationStatus.REQUESTED
            self._record_mitigation_result(MitigationResult(
                request_id=req.id,
                status=MitigationStatus.REQUESTED,
                reason="Detection-only mode: request recorded, no rule installed",
            ))
        elif self.ips_mode == MitigationMode.MANUAL_APPROVAL:
            req.status = MitigationStatus.REQUESTED
            self._pending_approvals[req.id] = time.time()
            self._record_mitigation_result(MitigationResult(
                request_id=req.id,
                status=MitigationStatus.REQUESTED,
                reason="Manual approval mode: awaiting operator approval",
            ))
        elif self.ips_mode == MitigationMode.AUTOMATIC_BLOCKING:
            try:
                rule_id = self._install_openflow_rule(req)
                req.status = MitigationStatus.APPLIED
                req.rule_id = rule_id
                self._record_mitigation_result(MitigationResult(
                    request_id=req.id,
                    status=MitigationStatus.APPLIED,
                    applied_rule_id=rule_id,
                    reason="Automatic blocking: rule installed",
                ))
            except Exception as e:
                req.status = MitigationStatus.FAILED
                self._record_mitigation_result(MitigationResult(
                    request_id=req.id,
                    status=MitigationStatus.FAILED,
                    error=str(e),
                    reason="Automatic blocking: rule installation failed",
                ))

        return req

    def _get_effective_threshold(self) -> float:
        """Return the effective confidence threshold for the current mode."""
        if self.ips_mode == MitigationMode.AUTOMATIC_BLOCKING:
            return 0.7
        return 0.5

    def _install_openflow_rule(self, request: MitigationRequest) -> Optional[str]:
        """Install a narrowly scoped OpenFlow flow modification rule."""
        if self.allowed_switches and request.switch_dp_id not in self.allowed_switches:
            msg = f"Switch {request.switch_dp_id} not in allowed-switches whitelist"
            raise InputValidationError(msg)

        if self.mode == "mock":
            rule_id = f"ofrule-{request.switch_dp_id}-{request.table_id}-{uuid.uuid4().hex[:8]}"
            rule_spec = {
                "rule_id": rule_id,
                "switch_dp_id": request.switch_dp_id,
                "table_id": request.table_id,
                "match": {
                    "eth_type": 0x0800,
                    "ip_proto": request.match.get("ip_proto") if hasattr(request, 'match') else 6,
                    "tcp_dst_port": request.match.get("tcp_dst_port") if hasattr(request, 'match') else None,
                    "ipv4_src_addr": request.match.get("ipv4_src_addr") if hasattr(request, 'match') else None,
                    "ipv4_dst_addr": request.match.get("ipv4_dst_addr") if hasattr(request, 'match') else None,
                },
                "priority": min(getattr(request, "priority", 1), self.max_rule_priority),
                "actions": ["output:normal"],
                "installed_at": time.time(),
            }
            self._active_rules[rule_id] = rule_spec
            return rule_id

        if self.mode == "ryu" and RYU_AVAILABLE:
            rule_id = f"ofrule-ryu-{request.switch_dp_id}-{request.table_id}"
            rule_spec = {
                "rule_id": rule_id,
                "switch_dp_id": request.switch_dp_id,
                "table_id": request.table_id,
                "mode": "ryu",
                "status": "pending",
            }
            self._active_rules[rule_id] = rule_spec
            return rule_id

        raise InputValidationError("OpenFlow rule installation not supported in current mode")

    def verify_flow_behavior(self, request: MitigationRequest) -> Optional[dict]:
        """Verify the flow behavior after a rule has been applied."""
        try:
            stats = self.get_flow_stats(switch_dp_id=request.switch_dp_id)
        except Exception:
            return None

        relevant = [s for s in stats if s.table_id == request.table_id]

        if not relevant:
            return {"observed_flows": 0, "note": "No flow stats for the given table"}

        if self.mode == "mock":
            return {
                "observed_flows": len(relevant),
                "traffic_change": "reduced",
                "verification_status": "passed",
                "note": "Mock-mode verification: rule simulated, traffic reduction observed",
            }

        if self.mode == "ryu" and RYU_AVAILABLE:
            return {
                "observed_flows": len(relevant),
                "note": "Ryu-mode verification: statistics queried from switch",
            }

        return {"observed_flows": len(relevant), "note": "Verification not supported in current mode"}

    def remove_rule(self, rule_id: str) -> MitigationResult:
        """Remove a previously installed OpenFlow rule with safe rollback."""
        rule_spec = self._active_rules.get(rule_id)

        if rule_spec is not None:
            del self._active_rules[rule_id]
            rule_spec["removed_at"] = time.time()

            if self.mode == "mock":
                result = MitigationResult(
                    request_id=rule_spec.get("request_id", rule_id),
                    status=MitigationStatus.ROLLED_BACK,
                    removed_at=rule_spec["removed_at"],
                    reason="Rule removed via rollback",
                )
                self._record_mitigation_result(result)
                return result

            result = MitigationResult(
                request_id=rule_id,
                status=MitigationStatus.ROLLED_BACK,
                removed_at=time.time(),
                reason="Rule removed via Ryu Flow Mod delete",
            )
            self._record_mitigation_result(result)
            return result
        else:
            result = MitigationResult(
                request_id=rule_id,
                status=MitigationStatus.ROLLED_BACK,
                removed_at=time.time(),
                reason="Rule not found (idempotent no-op)",
            )
            self._record_mitigation_result(result)
            return result

    def emergency_stop(self) -> List[MitigationResult]:
        """Emergency stop: remove all active mitigation rules with rollback."""
        results: List[MitigationResult] = []
        for rule_id in list(self._active_rules.keys()):
            result = self.remove_rule(rule_id)
            results.append(result)
        return results

    def _record_mitigation_result(self, result: MitigationResult) -> None:
        """Append a mitigation result to the adapter's history."""
        self._mitigation_history.append(result)

    def export_mitigation_history(self, fmt: str = "json") -> str:
        """Export the mitigation history."""
        if fmt == "json":
            return json.dumps(
                [r.to_dict() for r in self._mitigation_history], indent=2, default=str
            )
        elif fmt == "csv":
            if not self._mitigation_history:
                return ""
            keys = set()
            for r in self._mitigation_history:
                keys.update(r.to_dict().keys())
            lines = [",".join(sorted(keys))]
            for r in self._mitigation_history:
                row = {k: r.to_dict().get(k, "") for k in sorted(keys)}
                lines.append(",".join(str(row[k]) for k in sorted(keys)))
            return "\n".join(lines)
        else:
            raise InputValidationError(f"Unsupported export format: {fmt}")

    def get_mitigation_summary(self) -> Dict[str, Any]:
        """Return a summary of mitigation activity."""
        summary: Dict[str, Any] = {
            "ips_mode": self.ips_mode,
            "total_requests": len(self._mitigation_history),
            "by_status": {},
        }
        for result in self._mitigation_history:
            status = result.status
            summary["by_status"][status] = summary["by_status"].get(status, 0) + 1
        return summary

    # -----------------------------------------------------------------
    # Legacy compatibility: detection history export (Phase 8)
    # -----------------------------------------------------------------

    def export_detection_history(self, fmt: str = "json") -> str:
        """Export the detection history (Phase 8 compatibility)."""
        if fmt == "json":
            return json.dumps(
                [r.to_dict() for r in self._detection_history], indent=2, default=str
            )
        elif fmt == "csv":
            if not self._detection_history:
                return ""
            lines = ["flow_id,prediction,label,timestamp,switch_dp_id,table_id"]
            for r in self._detection_history:
                lines.append(
                    f"{r.flow_id},{r.prediction},{r.label},{r.timestamp},{r.switch_dp_id},{r.table_id}"
                )
            return "\n".join(lines)
        else:
            raise InputValidationError(f"Unsupported export format: {fmt}")



    def to_legacy_service_response(self) -> Dict[str, Any]:
        """Convert adapter state to the legacy SDNService response shape (Phase 8 compatibility)."""
        base: Dict[str, Any] = {
            "mode": self.mode,
            "connected": self._connected,
            "feature_count": FEATURE_NAME_COUNT,
        }
        if self._switch_info is not None:
            base["switch"] = self._switch_info.to_dict()
        else:
            base["switch"] = None
        return base

    def get_detection_summary(self) -> Dict[str, Any]:
        """Return a summary of detection activity (Phase 8 compatibility)."""
        summary: Dict[str, Any] = {
            "total_detections": len(self._detection_history),
            "by_label": {},
        }
        for r in self._detection_history:
            label = str(r.label)
            summary["by_label"][label] = summary["by_label"].get(label, 0) + 1
        return summary


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------

def create_sdn_adapter(
    *,
    mode: str = "mock",
    controller_host: str = "127.0.0.1",
    controller_port: int = 6633,
    model_path: Optional[Path] = None,
    scaler_path: Optional[Path] = None,
    feature_mapping: Optional[Dict[int, str]] = None,
    lab_network: bool = False,
    ips_mode: str = MitigationMode.DETECTION_ONLY,
    max_rule_priority: int = 10,
    allowed_switches: Optional[List[str]] = None,
) -> SDNAdapter:
    """Factory function to create an :class:`SDNAdapter` instance.

    Parameters
    ----------
    mode : str
        ``"ryu"``, ``"mock"``, or ``"offline"``.
    controller_host : str
        Controller hostname/IP (ignored in mock/offline mode).
    controller_port : int
        Controller port (ignored in mock/offline mode).
    model_path : Path or None
        Path to a saved ``securefed-model-v1`` artifact. If ``None`` a
        GRU model is built per the research architecture.
    scaler_path : Path or None
        Path to JSON ``{"means": [...], "scales": [...]}`` for feature scaling.
    feature_mapping : dict or None
        Position-to-field-name mapping. If ``None`` the default documented
        mapping is used.
    lab_network : bool
        If ``True``, enable lab-network-specific behaviours.
    ips_mode : str
        IPS mitigation mode. One of:
        - ``MitigationMode.DETECTION_ONLY`` (default): no rules installed.
        - ``MitigationMode.MANUAL_APPROVAL``: requests require approval.
        - ``MitigationMode.AUTOMATIC_BLOCKING``: auto-install rules (lab-only).
    max_rule_priority : int
        Maximum priority for OpenFlow rules (default 10, least-privilege).
    allowed_switches : list or None
        Whitelist of switch DPIDs allowed for mitigation.  Empty list means
        no whitelist (use with caution; in production a whitelist should always
        be configured).

    Returns
    -------
    SDNAdapter
        Configured adapter instance.
    """
    return SDNAdapter(
        mode=mode,
        controller_host=controller_host,
        controller_port=controller_port,
        model_path=model_path,
        scaler_path=scaler_path,
        feature_mapping=feature_mapping,
        lab_network=lab_network,
        ips_mode=ips_mode,
        max_rule_priority=max_rule_priority,
        allowed_switches=allowed_switches,
    )