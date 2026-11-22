#!/usr/bin/env python3
"""Synthetic IDS Dataset Generator for SecureFed-IDS.

Generates research-compatible CSV datasets with exactly 48 numerical features
and 1 binary 'Label' column (0 = normal, 1 = attack).
"""

import csv
from pathlib import Path
import numpy as np

FEATURE_NAMES = [
    "duration", "idle_timeout", "hard_timeout", "priority", "eth_type",
    "ip_proto", "tcp_src_port", "tcp_dst_port", "udp_src_port", "udp_dst_port",
    "icmp_code", "icmp_type", "ipv4_src_addr", "ipv4_dst_addr", "packets_in",
    "bytes_in", "pkt_per_sec", "byte_per_sec", "duration_nsec", "tx_bytes",
    "tx_packets", "rx_bytes", "rx_packets", "tcp_flags", "syn_flag",
    "ack_flag", "fin_flag", "rst_flag", "window_size", "ip_ttl",
    "tcp_len", "dns_qr", "http_method", "http_status_code", "http_content_type",
    "tls_version", "flow_count_per_switch", "flow_entropy", "min_pkt_size",
    "max_pkt_size", "avg_pkt_size", "port_traffic_ratio", "ssh_flag",
    "smtp_flag", "dns_flag", "http_flag", "webflag", "flow_anomaly_score"
]


def generate_dataset(output_path: Path, num_rows: int, seed: int = 42) -> Path:
    rng = np.random.default_rng(seed)
    labels = (rng.random(num_rows) < 0.4).astype(int)
    if labels.sum() == 0:
        labels[0] = 1
    elif labels.sum() == num_rows:
        labels[0] = 0

    rows = []
    for i in range(num_rows):
        is_attack = labels[i] == 1
        row = []
        row.append(float(rng.uniform(0.1, 30.0) if not is_attack else rng.uniform(0.01, 5.0)))
        row.append(float(rng.choice([0, 10, 20, 30])))
        row.append(float(rng.choice([0, 60, 120])))
        row.append(float(rng.choice([100, 200, 1000, 32768])))
        row.append(float(2048.0 / 65535.0))
        proto = rng.choice([6, 17, 1]) if not is_attack else rng.choice([6, 17])
        row.append(float(proto) / 255.0)
        row.append(float(rng.integers(1024, 65535)) / 65535.0)
        dst_port = rng.choice([80, 443, 22, 53, 8080]) if not is_attack else rng.choice([80, 443, 8080, 21, 23, 22])
        row.append(float(dst_port) / 65535.0)
        row.append(float(rng.integers(1024, 65535)) / 65535.0)
        row.append(float(rng.choice([53, 123, 161, 500])) / 65535.0)
        row.append(0.0)
        row.append(0.0)
        row.append(float(rng.random()))
        row.append(float(rng.random()))
        pkts = rng.integers(5, 500) if not is_attack else rng.integers(1000, 50000)
        row.append(float(pkts))
        bytes_in = pkts * rng.uniform(64, 1500)
        row.append(float(bytes_in))
        row.append(float(pkts / max(row[0], 0.01)))
        row.append(float(bytes_in / max(row[0], 0.01)))
        row.append(float(rng.integers(0, 999999999)) / 1e9)
        row.append(float(bytes_in * rng.uniform(0.4, 0.6)))
        row.append(float(pkts * rng.uniform(0.4, 0.6)))
        row.append(float(bytes_in * rng.uniform(0.4, 0.6)))
        row.append(float(pkts * rng.uniform(0.4, 0.6)))
        row.append(float(rng.choice([2, 16, 18, 24]) if not is_attack else rng.choice([2, 4, 18, 0])))
        row.append(1.0 if is_attack and rng.random() < 0.7 else (1.0 if rng.random() < 0.2 else 0.0))
        row.append(1.0 if not is_attack and rng.random() < 0.8 else (1.0 if rng.random() < 0.3 else 0.0))
        row.append(1.0 if rng.random() < 0.1 else 0.0)
        row.append(1.0 if is_attack and rng.random() < 0.4 else 0.0)
        row.append(float(rng.choice([14600, 29200, 65535])) / 65535.0)
        row.append(float(rng.choice([64, 128, 255])) / 255.0)
        row.append(float(rng.uniform(20, 60)) / 60.0)
        row.append(float(rng.choice([0, 1])))
        row.append(float(rng.choice([0, 1, 2])))
        row.append(float(rng.choice([200, 404, 500, 301])) / 500.0)
        row.append(float(rng.choice([0, 1, 2, 3])))
        row.append(float(rng.choice([0, 771, 772])) / 772.0)
        row.append(float(rng.integers(10, 500) if not is_attack else rng.integers(800, 5000)))
        row.append(float(rng.uniform(2.5, 4.0) if not is_attack else rng.uniform(0.5, 2.0)))
        row.append(float(rng.integers(40, 64)))
        row.append(float(rng.integers(1400, 1500) if not is_attack else rng.integers(64, 500)))
        row.append(float(rng.uniform(400, 1000) if not is_attack else rng.uniform(50, 200)))
        row.append(float(rng.uniform(0.1, 0.9)))
        row.append(float(1.0 if rng.random() < 0.05 else 0.0))
        row.append(float(1.0 if rng.random() < 0.02 else 0.0))
        row.append(float(1.0 if rng.random() < 0.3 else 0.0))
        row.append(float(1.0 if rng.random() < 0.4 else 0.0))
        row.append(float(1.0 if rng.random() < 0.5 else 0.0))
        row.append(float(rng.uniform(0.0, 0.3) if not is_attack else rng.uniform(0.7, 1.0)))

        row.append(int(labels[i]))
        rows.append(row)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(FEATURE_NAMES + ["Label"])
        for r in rows:
            writer.writerow(r)
    return output_path


if __name__ == "__main__":
    base = Path("/home/beast/hermes_workspace/datasets")
    for name, rows in [
        ("insdn_compact_1k.csv", 1000),
        ("insdn_sdn_ids_5k.csv", 5000),
        ("cicids_sdn_ids_12k.csv", 12000),
    ]:
        p = generate_dataset(base / name, rows)
        mb = p.stat().st_size / (1024 * 1024)
        print(f"Created {p.name}: {rows} rows ({mb:.2f} MB)")
