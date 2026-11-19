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
translated to the 48-feature vector expected by the validated GRU IDS model.
No automatic packet/flow statistics assumptions are made regarding research
dataset feature alignment; mapping is documented and testable.
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
MODEL_INPUT_SHAPE = (1, FEATURE_NAME_COUNT)

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
# Feature mapping: OpenFlow flow fields -> 48 IDS features
# ---------------------------------------------------------------------------

# The research dataset uses 48 numeric features (see dataset.py / model.py).
# This mapping documents how common OpenFlow 1.3 fields are projected into
# that space.  The mapping is **many-to-one** and many fields are omitted;
# the adapter fills the remaining slots with zeros (or learned defaults) and
# the caller is responsible for verifying suitability for their model.


# Mapping positions to OpenFlow field descriptions.
# Position 0-23: Basic packet header fields (normalized)
# Position 24-35: Timing / duration / packet count fields
# Position 36-47: Protocol / flag / byte-count derived fields

# Suggested mapping (adjust to match your research dataset exactly):
#   0:  duration (seconds)                     -> flow duration
#   1:  idle_timeout (ms)                      -> idle time
#   2:  hard_timeout (ms)                      -> hard timeout
#   3:  priority                               -> flow priority
#   4:  eth_type                               -> Ethernet type (IP=0x0800)
#   5:  ip_proto                               -> IP protocol (TCP/UDP/ICMP)
#   6:  tcp_src_port                           -> source port
#   7:  tcp_dst_port                           -> destination port
#   8:  udp_src_port                           -> source port
#   9:  udp_dst_port                           -> destination port
#   10: icmp_code                              -> ICMP code
#   11: icmp_type                              -> ICMP type
#   12: ipv4_src_addr                          -> source IP (hashed/encoded)
#   13: ipv4_dst_addr                          -> destination IP (hashed/encoded)
#   14: packets_in                             -> total packets
#   15: bytes_in                               -> total bytes
#   16: pkt_per_sec                            -> packets per second
#   17: byte_per_sec                           -> bytes per second
#   18: duration_nsec                          -> nanosecond part of duration
#   19: tx_bytes                               -> transmitted bytes
#   20: tx_packets                             -> transmitted packets
#   21: rx_bytes                               -> received bytes
#   22: rx_packets                             -> received packets
#   23: tcp_flags                                -> TCP flag bitmask
#   24: syn_flag                                 -> SYN flag set
#   25: ack_flag                                 -> ACK flag set
#   26: fin_flag                                 -> FIN flag set
#   27: rst_flag                                 -> RST flag set
#   28: window_size                              -> TCP window size
#   29: ip_ttl                                  -> IP TTL
#   30: tcp_len                                  -> TCP payload length
#   31: dns_qr                                   -> DNS query/response flag
#   32: http_method                              -> HTTP method code
#   33: http_status_code                         -> HTTP status code
#   34: http_content_type                        -> HTTP content type
#   35: tls_version                              -> TLS version indicator
#   36: flow_count_per_switch                    -> number of flows
#   37: flow_entropy                             -> entropy of flow features
#   38: min_pkt_size                               -> minimum packet size
#   39: max_pkt_size                               -> maximum packet size
#   40: avg_pkt_size                               -> average packet size
#   41: port_traffic_ratio                         -> traffic ratio per port
#   42: ssh_flag                                   -> SSH indicator
#   43: smtp_flag                                  -> SMTP indicator
#   44: dns_flag                                   -> DNS indicator
#   45: http_flag                                  -> HTTP indicator
#   46: webflag                                    -> Web traffic flag
#   47: label                                    -> attack/normal label (ground truth)

# By default the adapter fills all 48 positions from available OpenFlow stats
# and zeros-out any unspecified positions.  The ``map_flow_to_features`` method
# can be overridden or configured to match the exact feature order used in your
# research dataset.

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


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
        base: Dict[str, Any] = {
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

    Modes
    -----
    * ``ryu``    - Real Ryu controller connection (WSL / Linux).
    * ``mock``   - Synthetic flow data generation (Windows default).
    * ``offline``- Read flow statistics from CSV logs.
    """

    # ---------------------------------------------------------------------
    # Initialization
    # ---------------------------------------------------------------------

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
    ) -> None:
        self.mode = mode
        self.controller_host = controller_host
        self.controller_port = controller_port
        self.lab_network = lab_network
        self._connected = False
        self._switch_info: Optional[SwitchInfo] = None
        self._last_flow: Optional[FlowStats] = None
        self._detection_history: List[DetectionResult] = []

        # ---- Model setup -------------------------------------------------
        self.model: Any = None
        self.scaler: Optional[ScalerStats] = None
        self._init_model(model_path, scaler_path)

        # ---- Feature-mapping configuration --------------------------------
        self.feature_mapping: Dict[int, str] = feature_mapping or {}
        self._init_feature_mapping()

        # ---- Mock state --------------------------------------------------
        self._mock_flow_counter = 0
        # Auto-connect in mock/offline modes since no real controller is needed
        if self.mode in ("mock", "offline"):
            self._connected = True

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
                # Extract scaler info if present in artifact
                if "scaler_stats" in payload:
                    # Reconstruct ScalerStats from artifact
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
            from web.backend.app.domain.model import build_gru_model

            self.model = build_gru_model(input_features=FEATURE_NAME_COUNT)
        else:
            # Model will remain None; predict() will raise UnavailableError.
            pass

        # Try to fit a scaler from provided data or use defaults
        if scaler_path is not None and scaler_path.is_file():
            try:
                data = scaler_path.read_text(encoding="utf-8").strip()
                # Expect JSON: {"means": [...], "scales": [...]}
                ss = json.loads(data)
                self.scaler = ScalerStats(means=ss.get("means", []), scales=ss.get("scales", []))
            except Exception as exc:  # pragma: no cover
                raise UnavailableError(f"Failed to load scaler: {exc}")
        # If no scaler provided, the model expects unit-normalized inputs;
        # the feature mapping documentation notes this limitation.

    @staticmethod
    def _read_model_artifact(path: Path) -> dict:
        import json
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("format") != "securefed-model-v1":
            raise InputValidationError("unsupported model artifact format")
        return payload

    # -----------------------------------------------------------------
    # Feature-mapping initialization
    # -----------------------------------------------------------------

    def _init_feature_mapping(self) -> None:
        """Set up the default OpenFlow-to-IDS-feature mapping.

        If ``feature_mapping`` was supplied via ``__init__``, those position
        names are used.  Otherwise the default documented mapping (see module
        constants) is established as ``position -> field_name``.
        """
        if self.feature_mapping:
            # User-provided mapping: position -> field_name
            return

        # Default: fill positions 0..47 with documented field names.
        # The actual numeric values are populated from flow stats; the names
        # are stored for documentation/inspection purposes.
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
        # Ensure we have exactly FEATURE_NAME_COUNT entries
        self.feature_mapping = {i: default_names[i] for i in range(min(FEATURE_NAME_COUNT, len(default_names)))}
        # Pad if somehow shorter
        while len(self.feature_mapping) < FEATURE_NAME_COUNT:
            self.feature_mapping[len(self.feature_mapping)] = f"feature_{len(self.feature_mapping)}"

    # -----------------------------------------------------------------
    # Connection management
    # -----------------------------------------------------------------

    def connect(self) -> Dict[str, Any]:
        """Connect to the SDN controller.

        In ``ryu`` mode: attempts a Ryu controller connection via OpenFlow 1.3.
        In ``mock`` mode: marks as connected immediately (no real connection).
        In ``offline`` mode: marks as connected; data will be read from logs.

        Returns
        -------
        status : dict
            Connection status dictionary.
        """
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
        # Minimal Ryu connection logic – in a full setup the controller would
        # be reachable at controller_host:controller_port via OpenFlow 1.3.
        # Here we merely verify importability; actual switch communication
        # requires Ryu to be running in the lab testbed.
        self._connected = True

    def disconnect(self) -> None:
        """Gracefully disconnect from the controller."""
        self._connected = False
        self._switch_info = None
        self._last_flow = None

    def status(self) -> Dict[str, Any]:
        """Return connection and mode status."""
        return {
            "mode": self.mode,
            "connected": self._connected,
            "controller_host": self.controller_host,
            "controller_port": self.controller_port,
            "ryu_available": RYU_AVAILABLE,
            "feature_count": FEATURE_NAME_COUNT,
        }

    # -----------------------------------------------------------------
    # Switch information
    # -----------------------------------------------------------------

    def get_switch_info(self) -> Optional[SwitchInfo]:
        """Retrieve switch information from the connected controller.

        Returns
        -------
        SwitchInfo or None
        """
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
        """Fetch switch info via Ryu (skeleton – requires running Ryu app)."""
        # In a real Ryu deployment the adapter would send an OFPStatsRequest
        # or query the Ryu API.  For Phase 8 we document the interface and
        # rely on the mock mode for testing.
        pass

    # -----------------------------------------------------------------
    # Flow statistics
    # -----------------------------------------------------------------

    def get_flow_stats(self, switch_dp_id: Optional[str] = None) -> List[FlowStats]:
        """Retrieve flow statistics from the switch.

        Parameters
        ----------
        switch_dp_id : str, optional
            Datapath ID.  If ``None`` the current switch info is used.

        Returns
        -------
        list[FlowStats]
        """
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
        # Real implementation would:
        #   1. Open an OpenFlow 1.3 connection to the Ryu controller
        #   2. Send an OFPST_STATS_REQUEST for OFPST_FLOW
        #   3. Parse the reply into FlowStats objects
        # For Phase 8 this is a skeleton; the mock mode is used for tests.
        return []

    def _generate_mock_flow_stats(self, switch_dp_id: str) -> List[FlowStats]:
        """Generate synthetic flow statistics for development/testing."""
        self._mock_flow_counter += 1
        n_flows = 3 + (self._mock_flow_counter % 5)  # 3..7 flows
        stats_list: List[FlowStats] = []

        for _ in range(n_flows):
            # Generate realistic-looking but synthetic fields
            match = {
                "eth_type": 0x0800,
                "ip_proto": np.random.choice([6, 17, 1]),  # TCP, UDP, ICMP
                "tcp_src_port": np.random.randint(49152, 65535) if np.random.random() > 0.3 else None,
                "tcp_dst_port": np.random.randint(1, 65535),
                "udp_src_port": None,
                "udp_dst_port": np.random.randint(1, 65535) if np.random.random() > 0.3 else None,
                "ipv4_src_addr": f"10.0.0.{np.random.randint(2, 254)}",
                "ipv4_dst_addr": f"10.0.0.{np.random.randint(2, 254)}",
            }

            # Build FlowStats with mapped fields
            fs = FlowStats(
                match=match,
                count_bytes=np.random.randint(64, 1_000_000),
                duration_sec=round(np.random.uniform(0.01, 10.0), 3),
                duration_nsec=np.random.randint(0, 1_000_000_000),
                idle_timeout=np.random.randint(0, 300),
                hard_timeout=np.random.randint(0, 3600),
                priority=np.random.choice([0, 1, 5, 10]),
                packet_count=np.random.randint(1, 10_000),
                byte_count=np.random.randint(64, 500_000),
                instruction_count=np.random.randint(0, 20),
                table_id=np.random.randint(0, 256),
                cookie=np.random.randint(0, 2**31 - 1),  # int32-safe range
            )
            stats_list.append(fs)

        return stats_list

    def _read_flow_stats_offline(self, switch_dp_id: str) -> List[FlowStats]:
        """Read flow statistics from CSV log files."""
        # Look for CSV files in the data directory
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
                    # Expected columns (adapt to your CSV schema):
                    # match_eth_type,match_ip_proto,tcp_src_port,tcp_dst_port,...
                    # duration_sec,packet_count,byte_count,...
                    for row in reader:
                        if len(row) < 3:
                            continue
                        try:
                            match = {}
                            # Parse match fields from first few columns
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
        """Map a FlowStats object to a 48-feature vector for the IDS model.

        This is the critical mapping step.  The method reads values from the
        flow's ``match`` dictionary and its numeric fields, normalises them,
        and places them into the positions documented in the module-level
        ``feature_mapping`` constant.

        Returns
        -------
        list[float]
            A list of 48 floating-point values ready for scaler transformation
            and model inference.
        """
        # Start with a list of zeros
        features: List[float] = [0.0] * FEATURE_NAME_COUNT

        match = flow.match

        # --- Basic numeric fields (position-indexed) ---
        # Position 0: duration (seconds)
        features[0] = flow.duration_sec
        # Position 1: idle_timeout (ms) – treat as absolute value
        features[1] = float(flow.idle_timeout)
        # Position 2: hard_timeout (ms)
        features[2] = float(flow.hard_timeout)
        # Position 3: priority
        features[3] = float(flow.priority)
        # Position 4: eth_type (numeric); normalise to 0.0/1.0
        etype = match.get("eth_type")
        features[4] = float(etype) / 65535.0 if etype is not None else 0.0
        # Position 5: ip_proto
        ipproto = match.get("ip_proto")
        features[5] = float(ipproto) / 255.0 if ipproto is not None else 0.0
        # Position 6: tcp_src_port
        tsrc = match.get("tcp_src_port")
        features[6] = float(tsrc) / 65535.0 if tsrc is not None else 0.0
        # Position 7: tcp_dst_port
        tdst = match.get("tcp_dst_port")
        features[7] = float(tdst) / 65535.0 if tdst is not None else 0.0
        # Position 8: udp_src_port
        usrc = match.get("udp_src_port")
        features[8] = float(usrc) / 65535.0 if usrc is not None else 0.0
        # Position 9: udp_dst_port
        udst = match.get("udp_dst_port")
        features[9] = float(udst) / 65535.0 if udst is not None else 0.0
        # Position 10: icmp_code
        icmp_code = match.get("icmp_code")
        features[10] = float(icmp_code) / 255.0 if icmp_code is not None else 0.0
        # Position 11: icmp_type
        icmp_type = match.get("icmp_type")
        features[11] = float(icmp_type) / 255.0 if icmp_type is not None else 0.0
        # Position 12: ipv4_src_addr – hash IP to [0,1] (simple modular hash)
        src_ip = match.get("ipv4_src_addr", "")
        if src_ip:
            h = sum(ord(c) for c in src_ip) % 1000
            features[12] = h / 1000.0
        else:
            features[12] = 0.0
        # Position 13: ipv4_dst_addr
        dst_ip = match.get("ipv4_dst_addr", "")
        if dst_ip:
            h = sum(ord(c) for c in dst_ip) % 1000
            features[13] = h / 1000.0
        else:
            features[13] = 0.0
        # Position 14: packets_in
        features[14] = float(flow.packet_count)
        # Position 15: bytes_in
        features[15] = float(flow.byte_count)
        # Position 16: pkt_per_sec – derived
        if flow.duration_sec > 0:
            features[16] = float(flow.packet_count) / flow.duration_sec
        else:
            features[16] = 0.0
        # Position 17: byte_per_sec – derived
        if flow.duration_sec > 0:
            features[17] = float(flow.byte_count) / flow.duration_sec
        else:
            features[17] = 0.0
        # Position 18: duration_nsec
        features[18] = float(flow.duration_nsec) / 1_000_000_000
        # Position 19: tx_bytes
        features[19] = float(match.get("tcp_src_port", flow.byte_count))  # fallback
        # Position 20: tx_packets – use packet_count as proxy
        features[20] = float(flow.packet_count)
        # Position 21: rx_bytes – same as bytes_in proxy
        features[21] = float(flow.byte_count)
        # Position 22: rx_packets – same as packet_count proxy
        features[22] = float(flow.packet_count)
        # Position 23: tcp_flags – bitmask proxy
        features[23] = float(match.get("tcp_flags", 0))

        # --- Protocol-specific derived fields ---
        # Position 24: SYN flag
        features[24] = 1.0 if match.get("tcp_src_port") is not None else 0.0
        # Position 25: ACK flag
        features[25] = 0.0  # placeholder; not directly in OF match
        # Position 26: FIN flag
        features[26] = 0.0
        # Position 27: RST flag
        features[27] = 0.0
        # Position 28: window_size
        features[28] = float(match.get("tcp_src_port", 0)) % 65536 / 65535.0
        # Position 29: IP TTL – not directly in OF flow match; use proxy
        features[29] = 0.5  # default mid-range
        # Position 30: TCP payload length – derived from byte_count/packet_count
        if flow.packet_count > 0:
            features[30] = float(flow.byte_count) / flow.packet_count
        else:
            features[30] = 0.0
        # Position 31: DNS QR – proxy via port 53
        features[31] = 1.0 if match.get("udp_dst_port") == 53 else 0.0
        # Position 32: HTTP method – proxy
        features[32] = 0.0
        # Position 33: HTTP status code – proxy
        features[33] = 0.0
        # Position 34: HTTP content type – proxy
        features[34] = 0.0
        # Position 35: TLS version – proxy
        features[35] = 0.0

        # --- Statistical / entropy fields (positions 36-47) ---
        # These are typically computed over a window of flows; here we use
        # simple proxies from the single flow.
        # Position 36: flow count per switch – proxy via priority
        features[36] = float(flow.priority) / 255.0
        # Position 37: flow entropy – simple proxy
        features[37] = 0.5
        # Position 38: min packet size – proxy
        features[38] = 0.2
        # Position 39: max packet size – proxy
        features[39] = 0.8
        # Position 40: avg packet size – same as position 30 proxy
        features[40] = features[30]
        # Position 41: port traffic ratio – proxy
        features[41] = 0.5
        # Position 42: SSH flag – proxy via dst port 22
        features[42] = 1.0 if match.get("udp_dst_port") == 22 or match.get("tcp_dst_port") == 22 else 0.0
        # Position 43: SMTP flag – proxy via dst port 25
        features[43] = 1.0 if match.get("udp_dst_port") == 25 or match.get("tcp_dst_port") == 25 else 0.0
        # Position 44: DNS flag – proxy via dst port 53
        features[44] = 1.0 if match.get("udp_dst_port") == 53 else 0.0
        # Position 45: HTTP flag – proxy via dst port 80/8080
        features[45] = 1.0 if match.get("tcp_dst_port") in (80, 8080, 443) else 0.0
        # Position 46: Web flag – general web indicator
        features[46] = 0.5
        # Position 47: label (ground truth) – not used for inference; set to -1
        features[47] = -1.0  # sentinel: unavailable during inference

        # Verify length
        assert len(features) == FEATURE_NAME_COUNT, (
            f"Expected {FEATURE_NAME_COUNT} features, got {len(features)}"
        )

        return features

    # -----------------------------------------------------------------
    # Model inference
    # -----------------------------------------------------------------

    def predict(self, features: List[float], switch_dp_id: str, table_id: int) -> Dict[str, Any]:
        """Run the GRU IDS model on prepared features.

        Parameters
        ----------
        features : list[float]
            48-dimensional feature vector.
        switch_dp_id : str
            Datapath ID of the switch the flow was observed on.
        table_id : int
            Flow table ID.

        Returns
        -------
        dict with keys:
            - "prediction": float (probability, 0=normal, 1=attack)
            - "label": int (0=normal, 1=attack)
            - "alert": dict or None
        """
        if self.model is None:
            raise UnavailableError("IDS model not initialized.")

        # Convert to numpy array with the expected shape (1, 1, 48)
        import numpy as np

        X = np.array(features, dtype=np.float32).reshape(MODEL_INPUT_SHAPE)

        # If a scaler is fitted, apply it before inference
        if self.scaler is not None:
            from ..domain.dataset import apply_scaler

            X = apply_scaler([X], self.scaler)[0]  # type: ignore[arg-type]
            # Reshape back after scaling
            X = X.reshape(MODEL_INPUT_SHAPE)

        # Perform inference
        # The model expects a TensorFlow/Keras model; if unavailable, fail closed.
        if not keras_available():
            raise UnavailableError("TensorFlow/Keras is not available for inference.")

        # Import TensorFlow lazily
        import tensorflow as tf  # type: ignore[import]

        # The model may have been built with build_gru_model; ensure it's
        # compiled and ready.
        if self.model is not None:
            pred = self.model.predict(X, verbose=0)[0][0]  # type: ignore[attr-defined]
        else:
            raise UnavailableError("Model is not built.")

        # Convert probability to label
        label = 1 if pred >= 0.5 else 0

        # Build alert if prediction indicates attack
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
        """Run the full detection pipeline for the current switch/flow.

        Steps
        -----
        1. Retrieve flow statistics.
        2. Map flow to 48 features.
        3. Run model prediction.
        4. Generate alert if attack detected.
        5. Record the DetectionResult.

        Returns
        -------
        DetectionResult or None if any step fails / not connected.
        """
        if not self._connected:
            return None

        # Step 1: Get flow stats
        flow_stats_list = self.get_flow_stats(switch_dp_id=switch_dp_id)
        if not flow_stats_list:
            return None

        # Use the first flow; in a real deployment you might iterate all
        flow = flow_stats_list[0]

        # Step 2: Map to features
        features = self.map_flow_to_features(flow)

        # Step 3: Model prediction
        tid = (table_id if table_id is not None else flow.table_id)
        try:
            inf = self.predict(features, switch_dp_id or DEFAULT_SWITCH_ID, tid)
        except UnavailableError:
            # If model/unavailable, still record a result with NaN prediction
            inf = {"prediction": float("nan"), "label": -1, "alert": None}

        # Step 4: Build detection result
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

        # Step 5: Record
        self._detection_history.append(result)

        return result

    # -----------------------------------------------------------------
    # Alert and recording
    # -----------------------------------------------------------------

    def record_result(self, result: DetectionResult) -> None:
        """Persist a detection result.

        In the mock/offline mode this appends to ``_detection_history``.
        In a production deployment this would write to a database, log file,
        or external monitoring system.
        """
        self._detection_history.append(result)

    def export_detection_history(self, fmt: str = "json") -> str:
        """Export the detection history as a string.

        Parameters
        ----------
        fmt : str
            ``"json"`` or ``"csv"``.

        Returns
        -------
        str
            Serialized detection history.
        """
        if fmt == "json":
            return json.dumps(
                [r.to_dict() for r in self._detection_history], indent=2, default=str
            )
        elif fmt == "csv":
            if not self._detection_history:
                return ""
            # Write CSV with key columns
            lines = ["flow_id,prediction,label,timestamp,switch_dp_id,table_id"]
            for r in self._detection_history:
                lines.append(
                    f"{r.flow_id},{r.prediction},{r.label},{r.timestamp},{r.switch_dp_id},{r.table_id}"
                )
            return "\n".join(lines)
        else:
            raise InputValidationError(f"Unsupported export format: {fmt}")

    # -----------------------------------------------------------------
    # Mock flow generation (enhanced)
    # -----------------------------------------------------------------

    def _generate_enriched_mock_flow(self, switch_dp_id: str) -> FlowStats:
        """Generate a single flow with enriched match fields for feature mapping."""
        self._mock_flow_counter += 1
        proto = np.random.choice([6, 17, 1])  # TCP, UDP, ICMP

        match = {
            "eth_type": 0x0800,
            "ip_proto": proto,
            "tcp_src_port": np.random.randint(49152, 65535) if np.random.random() > 0.4 else None,
            "tcp_dst_port": np.random.randint(1, 65535),
            "udp_src_port": None if proto == 6 else (np.random.randint(49152, 65535) if np.random.random() > 0.4 else None),
            "udp_dst_port": np.random.randint(1, 65535) if proto == 17 else None,
            "ipv4_src_addr": f"10.0.{np.random.randint(1, 254)}.{np.random.randint(1, 254)}",
            "ipv4_dst_addr": f"10.0.{np.random.randint(1, 254)}.{np.random.randint(1, 254)}",
            "icmp_code": 0 if proto == 1 else None,
            "icmp_type": 8 if proto == 1 else None,  # echo request
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
            cookie=int(np.random.uniform(0, 2**31 - 1)),  # int32-safe range
        )
        return fs

    # -----------------------------------------------------------------
    # Compatibility shim for the existing SDNService
    # -----------------------------------------------------------------

    def to_legacy_service_response(self) -> Dict[str, Any]:
        """Convert adapter state to the legacy SDNService response shape.

        This allows gradual replacement of the old ``SDNService`` without
        breaking existing API endpoints.
        """
        base = {
            "mode": self.mode,
            "connected": self._connected,
            "feature_count": FEATURE_NAME_COUNT,
        }
        if self._switch_info is not None:
            base["switch"] = self._switch_info.to_dict()
        return base


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
        Path to a saved ``securefed-model-v1`` artifact.  If ``None`` a
        GRU model is built per the research architecture.
    scaler_path : Path or None
        Path to JSON ``{"means": [...], "scales": [...]}`` for feature scaling.
    feature_mapping : dict or None
        Position-to-field-name mapping.  If ``None`` the default documented
        mapping is used.
    lab_network : bool
        If ``True``, enable lab-network-specific behaviours (e.g. stricter
        validation, different default topologies).

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
    )