"""Simulated federated client.

The client holds one deterministic training shard. It is an in-process
simulation, not an independent runtime, and it has no authenticated session.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from typing import Sequence

from ...errors import InputValidationError
from .backends import TrainingBackend


@dataclass(frozen=True)
class ClientUpdate:
    client_id: str
    weights: tuple[float, ...]
    sample_count: int
    digest: str
    round_index: int

    def as_dict(self) -> dict[str, object]:
        return {
            "client_id": self.client_id,
            "sample_count": self.sample_count,
            "digest": self.digest,
            "round_index": self.round_index,
        }


def weight_digest(weights: Sequence[float]) -> str:
    """Reproducibility digest, not a signature or integrity control."""
    encoded = json.dumps([float(value) for value in weights], separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass
class SimulatedClient:
    client_id: str
    rows: list[list[float]]
    labels: list[int]
    seed: int

    def __post_init__(self) -> None:
        if not self.client_id:
            raise InputValidationError("client_id is required")
        if len(self.rows) != len(self.labels):
            raise InputValidationError("client feature and label row counts differ")
        if not self.rows:
            raise InputValidationError(f"client {self.client_id} has no training rows")
        width = len(self.rows[0])
        for row in self.rows:
            if len(row) != width:
                raise InputValidationError("client rows have inconsistent widths")

    @property
    def sample_count(self) -> int:
        return len(self.rows)

    def train(
        self,
        global_weights: Sequence[float],
        backend: TrainingBackend,
        *,
        round_index: int,
        epochs: int,
        batch_size: int,
        learning_rate: float,
    ) -> ClientUpdate:
        rng = random.Random((self.seed << 7) ^ (round_index * 0x9E3779B1))
        trained = backend.train(
            global_weights,
            self.rows,
            self.labels,
            epochs=epochs,
            batch_size=batch_size,
            learning_rate=learning_rate,
            rng=rng,
        )
        weights = tuple(float(value) for value in trained)
        return ClientUpdate(
            client_id=self.client_id,
            weights=weights,
            sample_count=self.sample_count,
            digest=weight_digest(weights),
            round_index=round_index,
        )
