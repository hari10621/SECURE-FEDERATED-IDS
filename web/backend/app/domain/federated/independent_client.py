"""Local process boundary for one client update of the plaintext GRU."""
from dataclasses import asdict
import hmac
import json
import secrets
from pathlib import Path
import subprocess
import sys

from ...errors import IntegrityError
from .client import ClientUpdate, SimulatedClient
from .keras_backend import KerasGRUBackend


class ProcessClient(SimulatedClient):
    def train(self, global_weights, backend, **options):
        token = secrets.token_hex(32)
        payload = {
            "client": asdict(self), "weights": global_weights, "options": options,
            "token": token,
        }
        completed = subprocess.run(
            [sys.executable, "-m", "app.domain.federated.independent_client"],
            cwd=Path(__file__).resolve().parents[3],
            input=json.dumps(payload), stdout=subprocess.PIPE, text=True, check=True,
        )
        response = json.loads(completed.stdout)
        if (response["client_id"] != self.client_id
                or response["round_index"] != options["round_index"]
                or response["sample_count"] != self.sample_count
                or not hmac.compare_digest(response.pop("token"), token)):
            raise IntegrityError("Worker response does not match the requested client round.")
        response["weights"] = tuple(response["weights"])
        return ClientUpdate(**response)


if __name__ == "__main__":
    payload = json.load(sys.stdin)
    client = SimulatedClient(**payload["client"])
    update = client.train(payload["weights"], KerasGRUBackend(), **payload["options"])
    json.dump({**asdict(update), "token": payload["token"]}, sys.stdout)
