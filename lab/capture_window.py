"""Measure a short host interface window from within its Mininet namespace."""

import collections
import json
import select
import socket
import struct
import sys
import time


def measure(interface):
    # rtnetlink via ip reads the current network namespace even where sysfs is shared.
    import subprocess

    def interface_counts():
        link = json.loads(
            subprocess.check_output(
                ["ip", "-j", "-s", "link", "show", "dev", interface]
            )
        )[0]
        stats = link.get("stats64") or link["stats"]
        return [
            stats["tx"]["packets"],
            stats["rx"]["packets"],
            stats["tx"]["bytes"],
            stats["rx"]["bytes"],
        ]

    flows = collections.Counter()
    values = []
    with socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3)) as sock:
        sock.bind((interface, 0))
        previous, start = interface_counts(), time.monotonic()
        for _ in range(12):
            deadline = start + 0.25
            while time.monotonic() < deadline:
                if not select.select(
                    [sock], [], [], max(0, deadline - time.monotonic())
                )[0]:
                    break
                frame = sock.recv(256)
                if len(frame) >= 34 and frame[12:14] == b"\x08\x00":
                    transport = 14 + 4 * (frame[14] & 15)
                    first_fragment = (int.from_bytes(frame[20:22], "big") & 0x1FFF) == 0
                    ports = (None, None)
                    if first_fragment and frame[23] in (6, 17) and 34 <= transport <= len(frame)-4:
                        ports = struct.unpack_from("!HH", frame, transport)
                    flows[
                        socket.inet_ntoa(frame[26:30]),
                        socket.inet_ntoa(frame[30:34]),
                        frame[23],
                        *ports,
                    ] += 1
            current, end = interface_counts(), time.monotonic()
            if any(a < b for a, b in zip(current, previous)):
                raise ValueError("Host interface counters reset during measurement.")
            values.extend((a - b) / (end - start) for a, b in zip(current, previous))
            previous, start = current, end
    return {
        "features": values,
        "observed_flows": [
            dict(source=s, destination=d, protocol=p, source_port=sp, destination_port=dp, packets=count)
            for (s, d, p, sp, dp), count in flows.most_common(100)
        ],
    }


if __name__ == "__main__":
    print(json.dumps(measure(sys.argv[1])))
