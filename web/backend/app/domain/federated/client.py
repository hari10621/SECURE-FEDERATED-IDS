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
from ..crypto.base import CentralizedCryptoBackend
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


@dataclass(frozen=True)
class EncryptedClientUpdate:
    """Ciphertext-only update. The aggregation server never sees weights."""

    client_id: str
    chunks: tuple[bytes, ...]
    sample_count: int
    ciphertext_digest: str
    round_index: int
    auth_token: str
    timestamp: float
    nonce: str

    def as_dict(self) -> dict[str, object]:
        return {
            "client_id": self.client_id,
            "sample_count": self.sample_count,
            "ciphertext_digest": self.ciphertext_digest,
            "round_index": self.round_index,
            "chunk_count": len(self.chunks),
            "auth_token_present": bool(self.auth_token),
        }


def ciphertext_digest(chunks: Sequence[bytes]) -> str:
    """SHA-256 over length-prefixed serialized ciphertext chunks."""
    hasher = hashlib.sha256()
    for chunk in chunks:
        hasher.update(len(chunk).to_bytes(8, "big"))
        hasher.update(chunk)
    return hasher.hexdigest()


def delta_weights(
    local_weights: Sequence[float], global_weights: Sequence[float]
) -> list[float]:
    """Paper update rule: ``ΔW = W_local - W_global``."""
    if len(local_weights) != len(global_weights):
        raise InputValidationError("local and global weight counts differ")
    return [float(local) - float(global_) for local, global_ in zip(local_weights, global_weights)]


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

    def train_encrypted(
        self,
        global_weights: Sequence[float],
        backend: TrainingBackend,
        crypto: CentralizedCryptoBackend,
        *,
        round_index: int,
        epochs: int,
        batch_size: int,
        learning_rate: float,
        auth_token: str,
        timestamp: float,
        nonce: str,
    ) -> EncryptedClientUpdate:
        """Train locally, compute ΔW, and encrypt it with the public context."""
        update = self.train(
            global_weights,
            backend,
            round_index=round_index,
            epochs=epochs,
            batch_size=batch_size,
            learning_rate=learning_rate,
        )
        delta = delta_weights(update.weights, global_weights)
        chunks = tuple(crypto.encrypt_vector(delta))
        return EncryptedClientUpdate(
            client_id=self.client_id,
            chunks=chunks,
            sample_count=self.sample_count,
            ciphertext_digest=ciphertext_digest(chunks),
            round_index=round_index,
            auth_token=auth_token,
            timestamp=float(timestamp),
            nonce=nonce,
        )
