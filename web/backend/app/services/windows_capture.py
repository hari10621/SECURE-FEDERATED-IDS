"""Optional passive capture. Only aggregate IPv4/IPv6 metadata leaves the callback."""

import os
import time
from collections import Counter
from pathlib import Path

from ..errors import InputValidationError, UnavailableError


def capabilities():
    installed = (
        os.name == "nt"
        and (
            Path(os.environ.get("SystemRoot", r"C:\Windows"))
            / "System32"
            / "Npcap"
            / "wpcap.dll"
        ).is_file()
    )
    if not installed:
        return {
            "available": False,
            "reason": "Install Npcap on Windows to enable passive capture.",
            "interfaces": [],
        }
    try:
        from scapy.all import conf

        if not conf.use_pcap:
            raise RuntimeError("Scapy could not open Npcap.")
        interfaces = [
            dict(id=i.network_name, name=i.description or i.name)
            for i in conf.ifaces.values()
            if i.network_name
        ]
        return {
            "available": bool(interfaces),
            "reason": "" if interfaces else "No accessible capture interfaces.",
            "interfaces": interfaces,
        }
    except (ImportError, OSError, RuntimeError) as exc:
        return {
            "available": False,
            "reason": f"Install optional Scapy and check capture permissions. {exc}",
            "interfaces": [],
        }


def capture(app, ctx, p):
    from . import native_samples

    db_factory = app.sdn.db
    observations = []
    from scapy.all import IP, IPv6, TCP, UDP, ICMP, sniff

    if p["interface"] not in {i["id"] for i in capabilities()["interfaces"]}:
        raise InputValidationError("Interface is no longer available.")
    started = time.monotonic()
    while time.monotonic() - started < p["duration"]:
        ctx.check_cancelled()
        windows = []
        counts = Counter()
        sizes = Counter()

        def observe(pkt):
            addr = pkt.getlayer(IP) or pkt.getlayer(IPv6)
            if addr is None:
                return
            proto = (
                "TCP"
                if TCP in pkt
                else "UDP"
                if UDP in pkt
                else "ICMP"
                if ICMP in pkt
                else str(getattr(addr, "proto", getattr(addr, "nh", "other")))
            )
            key = (addr.src, addr.dst, proto)
            counts[key] += 1
            sizes[key] += len(pkt)
            if p.get("client") and not windows:
                observations.append(
                    (
                        float(pkt.time),
                        len(pkt),
                        int(addr.proto if IP in pkt else addr.nh),
                    )
                )
                if len(observations) == 13:
                    windows.append(native_samples.vector(observations))
                    observations.clear()

        try:
            sniff(
                iface=p["interface"],
                filter=f"(ip or ip6) and port {int(p['port'])}" if p.get("port") else "ip or ip6",
                store=False,
                promisc=False,
                prn=observe,
                timeout=min(1, max(0.01, p["duration"] - (time.monotonic() - started))),
            )
        except (OSError, RuntimeError) as exc:
            raise UnavailableError(
                f"Capture failed. Check interface permissions. {exc}"
            ) from exc
        with app.models.lock, db_factory() as db:
            for features in windows:
                native_samples.record(
                    app, db, "capture", p["client"], ctx.job_id, features
                )
            db.executemany(
                """INSERT INTO capture_flow VALUES(?,?,?,?,?,?) ON CONFLICT(job,src,dst,protocol)
               DO UPDATE SET packets=packets+excluded.packets,bytes=bytes+excluded.bytes""",
                [(ctx.job_id, *k, n, sizes[k]) for k, n in counts.items()],
            )
        ctx.progress(
            min(1, (time.monotonic() - started) / p["duration"]),
            "Collecting IP flow metadata",
        )
    return {"schema": "windows.ip.aggregate.v1"}
