# Phase 8 — SDN Network Emulation and Controller Integration

## Overview

This phase integrates SecureFed-IDS with an isolated SDN test environment using
Mininet, Open vSwitch, Ryu controller, and OpenFlow.

The core of this integration is the **modular SDN adapter** (`web/backend/app/services/sdn_adapter.py`)
which provides:

1. **Connect to the configured controller** — Ryu controller via OpenFlow 1.3,
   or mock mode for development on Windows.
2. **Read switch and flow information where supported** — switch DPID, ports,
   statistics.
3. **Receive flow statistics** — OpenFlow ``OFPTFlowStatsReply`` parsed into
   structured ``FlowStats`` objects.
4. **Map observed flows to the feature extraction pipeline** — documented
   OpenFlow-to-48-feature mapping (see *Feature Mapping* below).
5. **Pass correctly prepared features to the validated IDS model** — GRU model
   with 48 input features, with optional StandardScaler normalization.
6. **Receive the model prediction** — probability 0..1, label 0 (normal) or 1
   (attack).
7. **Produce an alert with flow identifiers and timestamp** — structured alert
   dict with flow ID, timestamp, prediction probability, and used features.
8. **Record the detection result** — persistent recording to history, exportable
   as JSON or CSV.

> **Important**: Flow statistics do not automatically match the research
> dataset features. The mapping is explicit, documented, and tested.  See the
> *Feature Mapping* section below.

---

## OS Requirements and Environment

| Component | Requirement | Notes |
|-----------|-------------|-------|
| **Host OS** | Windows 10/11 (tested on) | The adapter has a **mock mode** that runs natively on Windows. |
| **SDN Lab** | Linux (Ubuntu 20.04/22.04) or WSL2 | Mininet and Ryu run natively in Linux. WSL2 is the safest |
|           |           | isolated environment on Windows. |
| **WSL2** | Version 2 | Must be enabled via "Turn Windows features on/off". |
| **Docker** | Optional | Can be used as an alternative to Mininet. |

### Safest Isolated Environment: WSL2 + Ubuntu

1. **Enable WSL2**:
   - Open PowerShell as Administrator:
     `wsl --install`
   - Restart your computer.
   - Launch Ubuntu from the Start menu.

2. **Inside Ubuntu (WSL2)**:
   - Install Mininet:
     ```bash
     sudo apt update
     sudo apt install -y mininet openvswitch-switch
     ```
   - Install Ryu:
     ```bash
     pip3 install ryu
     ```
   - Start Ryu controller (in one terminal):
     ```bash
     ryu-manager --verbose ryu.app.simple_switch_13
     ```
   - Start Mininet (in another terminal):
     ```bash
     mn --controller c0,ip=127.0.0.1 --switch ovs,protocols=OpenFlow13
     ```

3. **Network isolation**: The WSL2 virtual switch is internal-only; it does
   not affect your host network adapter.  All traffic stays within the lab
   VM/WSL2 instance.

### Alternative: Docker-based SDN Lab

If Mininet installation in WSL2 proves difficult, a Docker container can
provide the same environment:

```bash
docker run -d --name sdn-lab \
  --net=host \
  -v $(pwd):/securefed \
  ryu/ryu:latest ryu-manager /securefed/ryu_app.py
```

---

## Topology Documentation

The recommended Phase 8 topology for testing is a **single-switch, single-host
setup**:

```
+--------+         +--------+
|  h1    |         |  s1    |
| (host) |         | (OVS)  |
+--------+         +--------+
   \               /
    \             /
     \           /
      \         /
       \       /
        \     /
         \   /
          \ /
       (Ryu Controller on c0, 127.0.0.1:6633)
```

### Node Descriptions

| Node | Role | IP/Address |
|------|------|------------|
| **h1** | Host (generator/capture) | 10.0.0.1/24 |
| **s1** | Open vSwitch | DPID: 00:00:00:00:00:00:00:01, 4 ports |
| **c0** | Ryu controller | 127.0.0.1:6633 (OpenFlow 1.3) |

### Flow Path

1. Host h1 generates traffic (e.g., HTTP, SSH, ICMP).
2. Switch s1 forwards packets and maintains flow entries.
3. Ryu controller receives ``OFPTFlowStatsRequest`` and replies with flow
   statistics.
4. The SDN adapter retrieves flow stats, maps them to 48 features, and
   runs the GRU IDS model.
5. If an attack is predicted, an alert is generated with the flow identifiers
   and timestamp.

### Custom Topologies

You can create more complex Mininet topologies using the Mininet Python API:
```python
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.link import TCLink

class SimpleTopo(Topo):
    def build(self):
        s1 = self.addSwitch('s1')
        h1 = self.addHost('h1', ip='10.0.0.1')
        h2 = self.addHost('h2', ip='10.0.0.2')
        self.addLink(h1, s1)
        self.addLink(h2, s1)

topo = SimpleTopo()
net = Mininet(topo=topo, controller='ryu')
net.start()
# ... run tests ...
net.stop()
```

---

## Feature Mapping: OpenFlow → 48-IDS-Feature Vector

This is the **critical** mapping step.  The research GRU model expects exactly
48 numeric features in a fixed order (see `web/backend/app/domain/dataset.py`
and `web/backend/app/domain/model.py`).  OpenFlow flow statistics provide many
of the same packet metadata, but the mapping is **not automatic** — it must be
explicitly configured and tested.

### Default Mapping (positions 0–47)

| Position | Field | Source | Normalisation |
|----------|-------|--------|---------------|
| 0 | duration (seconds) | `flow.duration_sec` | raw |
| 1 | idle_timeout (ms) | `flow.idle_timeout` | raw |
| 2 | hard_timeout (ms) | `flow.hard_timeout` | raw |
| 3 | priority | `flow.priority` | raw |
| 4 | eth_type | `match.eth_type` | /65535 |
| 5 | ip_proto | `match.ip_proto` | /255 |
| 6 | tcp_src_port | `match.tcp_src_port` | /65535 |
| 7 | tcp_dst_port | `match.tcp_dst_port` | /65535 |
| 8 | udp_src_port | `match.udp_src_port` | /65535 |
| 9 | udp_dst_port | `match.udp_dst_port` | /65535 |
| 10 | icmp_code | `match.icmp_code` | /255 |
| 11 | icmp_type | `match.icmp_type` | /255 |
| 12 | ipv4_src_addr | hashed IP | modular hash /1000 |
| 13 | ipv4_dst_addr | hashed IP | modular hash /1000 |
| 14 | packets_in | `flow.packet_count` | raw |
| 15 | bytes_in | `flow.byte_count` | raw |
| 16 | pkt_per_sec | derived | pkt/duration |
| 17 | byte_per_sec | derived | byte/duration |
| 18 | duration_nsec | `flow.duration_nsec` | /1e9 |
| 19 | tx_bytes | proxy | byte_count |
| 20 | tx_packets | proxy | packet_count |
| 21 | rx_bytes | proxy | byte_count |
| 22 | rx_packets | proxy | packet_count |
| 23 | tcp_flags | `match.tcp_flags` | raw |
| 24 | syn_flag | proxy | 1/0 |
| 25 | ack_flag | proxy | 1/0 |
| 26 | fin_flag | proxy | 1/0 |
| 27 | rst_flag | proxy | 1/0 |
| 28 | window_size | proxy | /65535 |
| 29 | ip_ttl | proxy | 0.5 (default) |
| 30 | tcp_len | derived | byte/pkt |
| 31 | dns_qr | proxy | 1 if UDP dst=53 |
| 32 | http_method | proxy | 0.0 (default) |
| 33 | http_status_code | proxy | 0.0 (default) |
| 34 | http_content_type | proxy | 0.0 (default) |
| 35 | tls_version | proxy | 0.0 (default) |
| 36 | flow_count_per_switch | proxy | /255 |
| 37 | flow_entropy | proxy | 0.5 (default) |
| 38 | min_pkt_size | proxy | 0.2 (default) |
| 39 | max_pkt_size | proxy | 0.8 (default) |
| 40 | avg_pkt_size | same as pos 30 | — |
| 41 | port_traffic_ratio | proxy | 0.5 (default) |
| 42 | ssh_flag | proxy | 1 if dst port=22 |
| 43 | smtp_flag | proxy | 1 if dst port=25 |
| 44 | dns_flag | proxy | 1 if dst port=53 |
| 45 | http_flag | proxy | 1 if dst port in (80,8080,443) |
| 46 | webflag | proxy | 0.5 (default) |
| 47 | label (ground truth) | **sentinel** | -1.0 (unavailable at inference) |

### Customising the Mapping

The mapping is defined by the ``feature_mapping`` dict passed to
``SDNAdapter.__init__()``:

```python
adapter = SDNAdapter(
    mode="ryu",
    feature_mapping={0: "duration", 1: "idle_timeout", ...},
)
```

If a custom mapping is provided, the **position number is the index into the
48‑feature vector**, and the **value is the field name** (for documentation/
inspection).  The actual numeric value is filled from the flow stat match fields
using the normalisation rules described above.

**To match your research dataset exactly**: inspect the `feature_names` from
your CSV loading code and adjust the mapping accordingly.  The test suite
(`test_sdn_adapter.py`) verifies that the mapping produces 48 float values
and that position 0 (duration) is positive when the flow has a non-zero
duration.

---

## Model Integration

The IDS model is the **GRU architecture** defined in
`web/backend/app/domain/model.py` with 48 input features:

- Input shape: ``(1, 1, 48)`` — 1 batch, 1 timestep, 48 features
- 3 GRU blocks: 256 → 128 → 64 units
- BatchNormalization + Dropout(0.3) after each GRU block
- Final Dense(1) with sigmoid activation
- Adam optimizer, binary_crossentropy loss, accuracy metric

### Model Loading

The adapter supports two modes:

1. **Build fresh model** (default): ``build_gru_model(input_features=48)``
   — works when TensorFlow/Keras is available.

2. **Load from artifact**: supply ``model_path`` pointing to a
   ``securefed-model-v1`` JSON artifact (see `model.py::artifact_filename`
   and `model.py::write_weight_artifact`).  The artifact must contain
   ``"weights"` (flat) and ``"parameter_specs"``.

### Scaler

If a scaler was fitted during training, provide its path via ``scaler_path``.
The scaler JSON format is:

```json
{"means": [0.0, ...], "scales": [1.0, ...]}
```

If no scaler is provided, the model expects unit-normalised inputs; the
feature mapping documentation notes this limitation.

---

## Alert Generation

When the GRU model predicts an attack (probability >= 0.5), the adapter
generates an alert:

```json
{
  "type": "intrusion_detected",
  "flow_id": "10.0.0.1-10.0.0.2-1",
  "timestamp": 1703030400.123,
  "prediction_probability": 0.87,
  "features_used": [0.1, 0.5, ...]
}
```

If the prediction is normal (probability < 0.5), no alert is generated
(`alert: None`).

---

## Result Recording

Every detection result is recorded in the adapter's internal history
``_detection_history`` list.  The history can be exported:

- **JSON**: ``adapter.export_detection_history(fmt="json")``
- **CSV**: ``adapter.export_detection_history(fmt="csv")``

Each entry contains: flow_id, timestamp, prediction, label, features,
switch_dp_id, table_id, and optionally the alert dict.

---

## Setup Instructions (Windows + WSL2)

### Prerequisites

1. **Windows** with WSL2 enabled:
   - PowerShell Admin: `wsl --install`
   - Restart

2. **Inside Ubuntu (WSL2)**:
   ```bash
   # Install dependencies
   sudo apt update
   sudo apt install -y python3-pip python3-venv git

   # Install Mininet
   sudo apt install -y mininet openvswitch-switch

   # Install Ryu
   pip3 install ryu

   # Install TensorFlow (for IDS model)
   pip3 install tensorflow
   ```

3. **Clone / ensure SecureFed-IDS is available**:
   ```bash
   git clone https://github.com/hari10621/SecureFed-IDS.git
   cd SecureFed-IDS
   ```

4. **Start Ryu controller** (in one WSL terminal):
   ```bash
   ryu-manager --verbose ryu.app.simple_switch_13
   ```

5. **Start Mininet** (in another WSL terminal):
   ```bash
   mn --controller c0,ip=127.0.0.1 --switch ovs,protocols=OpenFlow13
   ```

6. **Run the integration** (Python from the project root):
   ```bash
   cd C:\Users\HARIS\Desktop\SecureFed-IDS\web\backend
   python -c "
from app.services.sdn_adapter import create_sdn_adapter
adapter = create_sdn_adapter(mode='ryu')
print(adapter.status())
stats = adapter.get_flow_stats()
features = adapter.map_flow_to_features(stats[0])
result = adapter.detect()
print('Prediction:', result.prediction, 'Label:', result.label)
if result.alert:
    print('Alert:', result.alert)
"
   ```

### Configuration via Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECUREFED_SDN_MODE` | `mock` | ``ryu``, `mock`, or `offline` |
| `SECUREFED_CONTROLLER_HOST` | `127.0.0.1` | Ryu controller hostname |
| `SECUREFED_CONTROLLER_PORT` | `6633` | Ryu controller OpenFlow port |
| `SECUREFED_MODEL_PATH` | `None` | Path to model artifact |
| `SECUREFED_SCALER_PATH` | `None` | Path to scaler JSON |
| `SECUREFED_FEATURE_MAPPING` | `None` | JSON dict for custom mapping |

Example:
```powershell
# PowerShell
$env:SECUREFED_SDN_MODE = "ryu"
$env:SECUREFED_CONTROLLER_HOST = "192.168.56.1"
$env:SECUREFED_MODEL_PATH = "C:\models\cicids2017_gru.json"
```

---

## Integration Tests

The test suite is at `web/backend/tests/test_sdn_adapter.py`.  Tests cover:

- Adapter creation in mock/ryu/offline modes
- Connection status and switch information
- Flow statistics retrieval
- Flow-to-feature mapping (48 features)
- Model prediction pipeline (when TensorFlow available)
- Alert generation
- Result recording and JSON/CSV export
- Custom feature mapping
- Legacy service compatibility

Run the tests:

```bash
cd C:\Users\HARIS\Desktop\SecureFed-IDS\web\backend
python -m pytest tests/test_sdn_adapter.py -v
```

> **Note**: Some tests that require TensorFlow are skipped if Keras is not
> importable.  Mock-mode tests run without a controller or model.

---

## Known Constraints & Limitations

1. **No automatic blocking**: Phase 8 does NOT implement automatic flow rule
   installation to block attacks.  Detection results are recorded and alerts
   are produced, but no OpenFlow rules are pushed.  (Phase 9 would add this.)

2. **Feature mapping is explicit**: Flow statistics do not automatically match
   the research dataset features.  The mapping must be documented and tested
   for your specific dataset.  See the *Feature Mapping* section above.

3. **Not live detection**: This phase does not claim live IDS detection.  All
   testing is inside an isolated lab network.  Offline CSV data can be used
   for development, but predictions on live traffic require a running Ryu
   controller and validated feature pipeline.

4. **Windows native operation**: The adapter runs in mock mode on Windows
   without Mininet/Ryu.  For full SDN functionality, use WSL2 or Docker.

5. **Isolated lab only**: Do **not** alter the user's real network
   configuration.  All testing must stay inside the lab network.

6. **Ryu on Python 3.12**: Ryu 4.34 has build issues on Python 3.12 Windows.
   The adapter falls back to mock mode; use WSL2 Ryu for real controller
   integration.

---

## Phase 8 Approval Checklist

- [ ] SDN adapter module created and tested (`sdn_adapter.py`)
- [ ] Integration tests written (`test_sdn_adapter.py`)
- [ ] Existing `sdn_service.py` updated to wrap the new adapter
- [ ] Feature mapping documented and tested
- [ ] WSL2 setup guide written
- [ ] Topology documentation completed
- [ ] Model integration verified (GRU 48-feature pipeline)
- [ ] Alert generation and result recording verified
- [ ] **No automatic blocking implemented** (explicitly documented)
- [ ] **Testing confined to isolated lab network** (WSL2/Docker)
- [ ] **Windows real network config not altered**
- [ ] Push to GitHub and verify all 8 phases work

---

## Next Phase (Phase 9) — Summary

Phase 9 would build on this foundation by adding:

1. **Automatic mitigation** — push OpenFlow flow entries to block/redirect
   detected attacks.
2. **Flow rule install/deinstall** — Ryu ``add_flow`` / ``delete_flow``.
3. **Multi-switch topology support** — spanning tree, link aggregation.
4. **Real-time packet capture** — integration with tshark/sniffers.
5. **Confidence-based response** — gentle throttling vs. hard block.

> **Stop for approval before Phase 9.**  Confirm that the Phase 8
> integration is satisfactory and that the constraints above are acceptable.