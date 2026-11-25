"""Local process boundary for one client update of the plaintext GRU."""

from dataclasses import asdict
import base64
import hmac
import json
import os
import threading
import time
import secrets
from pathlib import Path
import subprocess
import sys

from ...errors import IntegrityError
from .client import (
    BroadcastPackage,
    ClientUpdate,
    EncryptedClientUpdate,
    SimulatedClient,
    weight_digest,
)
from .keras_backend import KerasGRUBackend


class ProcessClient(SimulatedClient):
    def train(self, global_weights, backend, **options):
        token = secrets.token_hex(32)
        payload = {
            "client": asdict(self),
            "weights": global_weights,
            "options": options,
            "token": token,
        }
        response = self.exchange(payload)
        if (
            response["client_id"] != self.client_id
            or response["round_index"] != options["round_index"]
            or response["sample_count"] != self.sample_count
            or not hmac.compare_digest(response.pop("token"), token)
        ):
            raise IntegrityError(
                "Worker response does not match the requested client round."
            )
        response["weights"] = tuple(response["weights"])
        return ClientUpdate(**response)

    def train_encrypted(self, global_weights, backend, crypto, **options):
        broadcast = options.pop("broadcast", None)
        encoded = lambda data: base64.b64encode(data).decode("ascii")
        package = (
            None
            if broadcast is None
            else {
                "round_index": broadcast.round_index,
                "hash": broadcast.hash,
                "chunks": [encoded(chunk) for chunk in broadcast.chunks],
            }
        )
        response = self.exchange(
            {
                "action": "encrypt",
                "client": asdict(self),
                "weights": global_weights,
                "options": options,
                "public": encoded(self.public_context),
                "broadcast": package,
            }
        )
        if (
            response["client_id"] != self.client_id
            or response["auth_token"] != options["auth_token"]
        ):
            raise IntegrityError("Encrypted worker identity mismatch")
        response["chunks"] = tuple(
            base64.b64decode(chunk, validate=True) for chunk in response["chunks"]
        )
        return EncryptedClientUpdate(**response)

    def exchange(self, payload):
        completed = subprocess.run(
            [sys.executable, "-m", "app.domain.federated.independent_client"],
            cwd=Path(__file__).resolve().parents[3],
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            text=True,
            check=True,
        )
        return json.loads(completed.stdout)


class Worker:
    def __init__(self, client_id):
        self.lock = threading.Lock()
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                "-m",
                "app.domain.federated.independent_client",
                client_id,
            ],
            cwd=Path(__file__).resolve().parents[3],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        try:
            hello = json.loads(self.process.stdout.readline())
            self.pid = int(hello["pid"])
            if hello["client_id"] != client_id:
                raise RuntimeError("Worker registration failed")
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
        self.process.wait()
        self.process.stdin.close()
        self.process.stdout.close()

    def exchange(self, payload):
        with self.lock:
            self.process.stdin.write(json.dumps(payload) + "\n")
            self.process.stdin.flush()
            reply = self.process.stdout.readline()
            if not reply:
                raise RuntimeError("Registered client disconnected during training")
            return json.loads(reply)


def train_payload(payload, backend):
    client = SimulatedClient(**payload["client"])
    started = time.monotonic()
    update = client.train(payload["weights"], backend, **payload["options"])
    return {
        **asdict(update),
        "training_seconds": time.monotonic() - started,
        "local_loss": backend.local_loss,
        "worker_pid": os.getpid(),
        "token": payload["token"],
    }


if __name__ == "__main__":
    backend = KerasGRUBackend()
    if len(sys.argv) == 1:
        json.dump(train_payload(json.load(sys.stdin), backend), sys.stdout)
    else:
        identity = sys.argv[1]
        print(json.dumps({"client_id": identity, "pid": os.getpid()}), flush=True)
        for line in sys.stdin:
            request = json.loads(line)
            if request["client"]["client_id"] != identity:
                raise IntegrityError("Worker identity mismatch")
            if request.get("action") == "sync":
                # Keep the reconstructed GRU resident until the next approved synchronization.
                deployed_model = backend.load_model(
                    request["weights"], 48, backend.learning_rate
                )
                import numpy as np

                installed = np.concatenate(
                    [block.ravel() for block in deployed_model.get_weights()]
                )
                if not np.array_equal(
                    installed, np.asarray(request["weights"], dtype=np.float32)
                ):
                    raise IntegrityError(
                        "Installed GRU weights differ from the approved bundle"
                    )
                deployed_version = request["version"]
                reply = {
                    "client_id": identity,
                    "pid": os.getpid(),
                    "version": deployed_version,
                    "digest": weight_digest(request["weights"]),
                    "token": request["token"],
                }
            elif request.get("action") == "encrypt":
                from ..crypto.tenseal_ckks import TensealCKKSBackend

                crypto = TensealCKKSBackend(
                    public_context=base64.b64decode(request["public"])
                )
                package = request["broadcast"]
                if package:
                    package["chunks"] = tuple(
                        base64.b64decode(v) for v in package["chunks"]
                    )
                local = SimulatedClient(**request["client"])
                update = local.train_encrypted(
                    request["weights"],
                    backend,
                    crypto,
                    broadcast=BroadcastPackage(**package) if package else None,
                    **request["options"],
                )
                reply = asdict(update)
                reply["chunks"] = [
                    base64.b64encode(chunk).decode("ascii") for chunk in update.chunks
                ]
            elif request.get("action") == "replay":
                reply = {
                    "features": request["features"],
                    "token": request["token"],
                    "client_id": identity,
                    "pid": os.getpid(),
                }
            else:
                reply = train_payload(request, backend)
            print(json.dumps(reply), flush=True)
