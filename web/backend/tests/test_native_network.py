import time
import pytest

ROOT = "/api/v1/native-network"


@pytest.mark.parametrize("layout", ["single", "linear", "star", "tree", "custom"])
def test_forwarding_and_lifecycle(client, layout):
    def change(op, **payload):
        response = client.post(ROOT + "/topology/" + op, json=payload)
        assert response.is_success, response.text

    change("create", topology=layout)
    assert client.post(ROOT + "/topology/create", json={}).status_code == 409
    change("start")
    if layout == "custom":
        change("connect", node="h1", peer="s1")
        change("connect", node="s1", peer="h2")
    response = client.post(
        ROOT + "/traffic",
        json=dict(source="h1", dest="h2", scenario="Normal TCP", samples=2, rate=20),
    )
    assert response.is_success, response.text
    limit = time.monotonic() + 15
    while time.monotonic() < limit:
        result = client.get(ROOT).json()
        if result["packets"] == 2:
            break
        time.sleep(0.1)
    assert result["network"]["nodes"]["h2"]["rx"] == 2
    assert result["flows"] and result["bytes"] == 240
    assert all(
        e["details"]["outcome"] == "Incompatible model" and not e["event"]
        for e in result["events"]
    )
    change("stop")
    assert (
        client.post(
            ROOT + "/traffic", json=dict(source="h1", dest="h2", scenario="Normal TCP")
        ).status_code
        == 409
    )
    change("delete")
    assert client.get(ROOT).json()["network"] is None


def test_reviewed_virtual_dataset(client):
    worker = client.post("/api/v1/clients", json={"name": "Window reviewer"}).json()[
        "id"
    ]

    def post(path, body):
        r = client.post(ROOT + path, json=body)
        assert r.is_success, r.text
        return r.json()

    net = post("/topology/create", {})
    post("/topology/start", {})
    post("/topology/map", {"node": "h2", "client": worker})
    post(
        "/traffic",
        dict(
            source="h1",
            dest="h2",
            scenario="Normal HTTP",
            samples=52,
            rate=20,
            duration=60,
        ),
    )
    path = "/samples/simulation/" + net["id"]
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        rows = client.get(ROOT + path).json()
        if len(rows) >= 4:
            break
        time.sleep(0.1)
    assert len(rows) == 4
    detail = client.get(ROOT + "/sample/" + rows[0]["id"])
    assert detail.is_success, detail.text
    assert detail.json()["schema_id"] == "simulation.window.v1"
    assert len(detail.json()["features"]) == 48
    assert client.post(ROOT + "/publish/simulation/" + net["id"]).status_code == 409
    for idx, s in enumerate(rows):
        assert s["outcome"] == "Incompatible model" and not s["event"]
        post(
            "/samples/" + s["id"] + "/review",
            dict(label=idx % 2, evidence="Independent fixture annotation"),
        )
    data = post("/publish/simulation/" + net["id"], {})
    assert data["rows"] == 4
    ds = client.get("/api/v1/datasets/" + data["dataset"]).json()
    assert ds["feature_count"] == 48

@pytest.mark.skipif(not __import__("os").getenv("SECUREFED_TEST_NPCAP"), reason="requires authorized Windows loopback capture")
def test_npcap_loopback_only(client):
    import socket
    cap=client.get(ROOT+"/capture").json()
    iface=next((i for i in cap["interfaces"] if "loopback" in (i["name"]+i["id"]).lower()),None)
    assert iface,cap["reason"] or "No Npcap loopback device exposed"
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sink,socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as source:
        sink.bind(("127.0.0.1",0))
        source.bind(("127.0.0.1",0))
        port=sink.getsockname()[1]
        response=client.post(ROOT+"/capture",json=dict(interface=iface["id"],duration=5,port=port))
        assert response.is_success,response.text
        job=response.json()["job"]
        for _ in range(12):
            source.sendto(b"SecureFed capture check",("127.0.0.1",port))
            time.sleep(.4)
        limit=time.monotonic()+12
        while time.monotonic()<limit:
            state=client.get("/api/v1/jobs/"+job).json()
            if state["status"] in ("succeeded","failed"):break
            time.sleep(.25)
        assert state["status"]=="succeeded",state
        rows=next(j["flows"] for j in client.get(ROOT+"/capture").json()["jobs"] if j["id"]==job)
        assert rows and all(f["src"]==f["dst"]=="127.0.0.1" and f["protocol"]=="UDP" for f in rows)
        assert sum(f["bytes"] for f in rows)>0
