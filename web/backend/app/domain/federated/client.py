"""Simulated federated client.

The client holds one deterministic training shard. It is an in-process
simulation, not an independent runtime. Supports authenticated sessions
and replay protection via round-index binding.
"""

from __future__ import annotations

import hashlib
import json
import time
import random
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Sequence

from ...errors import InputValidationError
from .backends import TrainingBackend


MAX_NONCE_AGE_SECONDS = 300


@dataclass(frozen=True)
class ClientAuthSession:
    client_id: str
    session_token: str
    created_at: datetime
    last_used: datetime

    def is_fresh(self) -> bool:
        return (datetime.now(timezone.utc) - self.last_used).total_seconds() < MAX_NONCE_AGE_SECONDS


@dataclass(frozen=True)
class ClientUpdate:
    client_id: str
    weights: tuple[float, ...]
    sample_count: int
    digest: str
    round_index: int
    session_token: str

    def as_dict(self) -> dict[str, object]:
        return {
            "client_id": self.client_id,
            "sample_count": self.sample_count,
            "digest": self.digest,
            "round_index": self.round_index,
            "session_token": self.session_token,
        }


def weight_digest(weights: Sequence[float], round_index: int = 0) -> str:
    """Reproducibility digest, not a signature or integrity control.

    Includes round_index so that the same weights in different rounds
    produce different digests, binding integrity to the round context.
    """
    encoded = json.dumps(
        [float(value) for value in weights], separators=(",", ":"),
    ) + f":round={round_index}"
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
            digest=weight_digest(weights, round_index=round_index),
            round_index=round_index,
            session_token="",
        )
