"""Loopback-only Mininet management service for a dedicated Ubuntu lab VM."""

import hmac
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import time
import uuid
from collections import deque
from http.server import BaseHTTPRequestHandler, HTTPServer

from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController


def command(*args):
    return subprocess.run(
        args, capture_output=True, text=True, timeout=5, check=True
    ).stdout.strip()


def config(data):
    topology = data["topology"]
    switches, hosts = data["switches"], data["hosts"]
    if (
        topology not in ("single", "linear", "tree")
        or not 1 <= switches <= 8
        or not 2 <= hosts <= 32
    ):
        raise ValueError("Choose 1-8 switches and 2-32 hosts.")
    if topology == "single" and switches != 1:
        raise ValueError("Single-switch topology requires exactly one switch.")
    subnet = ipaddress.IPv4Network(data["subnet"])
    if (
        not any(
            subnet.subnet_of(ipaddress.ip_network(block))
            for block in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
        )
        or subnet.num_addresses < hosts + 2
    ):
        raise ValueError("Choose a sufficiently large private IPv4 subnet.")
    address = ipaddress.IPv4Address(data["controller"])
    if not address.is_loopback or not 1 <= data["port"] <= 65535:
        raise ValueError("Use the isolated VM controller's loopback address and port.")
    return {**data, "subnet": str(subnet), "controller": str(address)}


class Lab:
    def __init__(self):
        self.spec = self.net = self.id = None
        self.history = deque(maxlen=120)
        self.last = None

    def create(self, data):
        if self.spec:
            raise ValueError("Delete the existing lab configuration first.")
        self.spec = config(data)
        self.id = uuid.uuid4().hex

    def start(self):
        if not self.spec or self.net:
            raise ValueError("Create a stopped lab before starting.")
        s = self.spec
        prefix = "sf" + self.id[:5]
        net = Mininet(
            controller=None,
            switch=OVSSwitch,
            build=False,
            ipBase=s["subnet"],
            autoSetMacs=True,
        )
        try:
            net.addController(
                "c0", controller=RemoteController, ip=s["controller"], port=s["port"]
            )
            switches = [
                net.addSwitch(
                    prefix + "s" + str(i + 1),
                    dpid=f"{i + 1:016x}",
                    protocols="OpenFlow13",
                    failMode="secure",
                )
                for i in range(s["switches"])
            ]
            for i in range(1, len(switches)):
                parent = (i - 1) // 2 if s["topology"] == "tree" else i - 1
                net.addLink(switches[parent], switches[i])
            for i in range(s["hosts"]):
                host = net.addHost("h" + str(i + 1))
                net.addLink(host, switches[i % len(switches)])
            net.build()
            net.start()
            net.waitConnected(timeout=3)
        except BaseException:
            net.stop()
            raise
        self.net = net
        self.history.clear()
        self.last = None

    def stop(self):
        if self.net:
            self.net.stop()
            self.net = None
        self.last = None
        self.history.clear()

    def snapshot(self):
        result = dict(
            protocol="securefed-lab-v1",
            lab_id=self.id,
            config=self.spec,
            running=bool(self.net),
            state="disconnected",
            reason="No active switch session.",
            hosts=[],
            switches=[],
            links=[],
            flows=[],
            history=[],
            packets=None,
        )
        if not self.net:
            return result
        net = self.net
        for sw in net.switches:
            connected = sw.connected()
            ports = {port.name: sw.ports[port] for port in sw.intfList()}
            result["switches"].append(
                dict(name=sw.name, dpid=sw.dpid, connected=connected, ports=ports)
            )
            dump = command("ovs-ofctl", "-O", "OpenFlow13", "dump-flows", sw.name)
            for line in dump.splitlines():
                if "actions=" in line:
                    result["flows"].append(dict(switch=sw.name, rule=line.strip()))
        for link in net.links:
            a, b = link.intf1, link.intf2
            result["links"].append(
                dict(
                    source=a.node.name,
                    target=b.node.name,
                    source_port=a.name,
                    target_port=b.name,
                    up=a.isUp() and b.isUp(),
                )
            )
        totals = [0, 0]
        for h in net.hosts:
            iface = h.defaultIntf()
            peer = iface.link.intf1 if iface == iface.link.intf2 else iface.link.intf2
            info = json.loads(h.cmd("ip -j -s link show dev", iface.name))[0]
            stats = info.get("stats64") or info["stats"]
            rx, tx = stats["rx"], stats["tx"]
            result["hosts"].append(
                dict(
                    name=h.name,
                    ip=h.IP(),
                    mac=h.MAC(),
                    switch=peer.node.name,
                    port=peer.node.ports[peer],
                    connected="LOWER_UP" in info["flags"],
                    tx_packets=tx["packets"],
                    rx_packets=rx["packets"],
                    tx_bytes=tx["bytes"],
                    rx_bytes=rx["bytes"],
                )
            )
            totals[0] += tx["packets"]
            totals[1] += tx["bytes"]
        now = time.monotonic()
        if self.last:
            then, packets, size = self.last
            if now - then >= 0.5 and totals[0] >= packets and totals[1] >= size:
                self.history.append(
                    dict(
                        time=time.time(),
                        pps=(totals[0] - packets) / (now - then),
                        bps=(totals[1] - size) / (now - then),
                    )
                )
        if self.last is None or now - self.last[0] >= 0.5:
            self.last = (now, *totals)
        active = sum(s["connected"] for s in result["switches"])
        result.update(
            history=list(self.history),
            packets=totals[0],
            state="connected"
            if active == len(net.switches)
            else "degraded"
            if active
            else "disconnected",
            reason=f"{active}/{len(net.switches)} OpenFlow 1.3 switch sessions established.",
        )
        return result

    def dispatch(self, action, data):
        if action in ("capture", "ping") and data.get("lab_id") != self.id:
            raise ValueError("Lab changed. Refresh the topology.")
        if action == "create":
            self.create(data)
        elif action == "start":
            self.start()
        elif action == "stop":
            self.stop()
        elif action == "delete":
            if self.net:
                raise ValueError("Stop the lab before deleting.")
            self.spec = self.id = None
        elif action == "capture":
            if not self.net or data.get("host") not in [h.name for h in self.net.hosts]:
                raise ValueError("Unknown lab host.")
            h = self.net[data["host"]]
            probe = None
            if data.get("normal_probe"):
                if h == self.net.hosts[-1]:
                    raise ValueError("Choose a destination other than the test host.")
                probe = self.net.hosts[-1].popen(
                    ["ping", "-n", "-W", "1", "-c", "5", "-i", "0.5", h.IP()],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            proc = h.popen(
                [
                    "/usr/bin/python3",
                    str(Path(__file__).with_name("capture_window.py")),
                    h.defaultIntf().name,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            out, err = proc.communicate(timeout=10)
            if probe:
                probe.wait(timeout=4)
            if proc.returncode:
                raise ValueError("Host capture failed: " + err.decode()[-200:])
            return json.loads(out)
        elif action == "ping":
            if not self.net or data.get("host") not in [
                h.name for h in self.net.hosts[:-1]
            ]:
                raise ValueError(
                    "Choose an active destination host other than the test host."
                )
            target = self.net[data["host"]]
            output = self.net.hosts[-1].cmd("ping -n -c 2 -W 1", target.IP())
            return dict(
                source=self.net.hosts[-1].IP(),
                destination=target.IP(),
                protocol="ICMP",
                output=output,
            )
        elif action != "snapshot":
            raise ValueError("Unknown lab action.")
        return self.snapshot()


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if not hmac.compare_digest(
            self.headers.get("Authorization", ""), "Bearer " + self.server.token
        ):
            self.send_error(403)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= 4096:
                raise ValueError("Invalid request size.")
            data = json.loads(self.rfile.read(length))
            result = self.server.lab.dispatch(self.path.removeprefix("/"), data)
            status = 200
        except (
            KeyError,
            TypeError,
            ValueError,
            RuntimeError,
            OSError,
            subprocess.SubprocessError,
        ) as exc:
            result, status = {"error": str(exc)}, 409
        reply = json.dumps(result).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)


if __name__ == "__main__":
    token = os.environ["SECUREFED_LAB_TOKEN"]
    if len(token) < 32:
        raise SystemExit("Set a lab token of at least 32 characters.")
    with HTTPServer(("127.0.0.1", 8765), Handler) as server:
        server.token, server.lab = token, Lab()
        try:
            server.serve_forever()
        finally:
            server.lab.stop()
