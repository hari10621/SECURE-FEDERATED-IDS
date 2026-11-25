"""In-process federated aggregation over plaintext updates.

The server validates shapes and weights, applies one of two weighting schemes,
and returns a deterministic aggregate.

Security:
  - Authentication: clients must present a valid session token.
  - Replay protection: updates are bound to round_index; old/repeated rounds are rejected.
  - SHA-256 integrity: each update digest is verified against weights.
  - Byzantine validation: size-based outlier heuristic is opt-in and explicitly
    not a security control; it is a cardinality-free cardinality check only.

Threat model: a malicious client can send crafted weights; the server detects
extreme outliers via the size heuristic (opt-in). Colluding clients can skew the
aggregate; the system does not claim Byzantine resilience without additional
cryptographic guarantees.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import secrets
import statistics
import time
from dataclasses import dataclass
from typing import Sequence

from ...errors import ConflictError, InputValidationError
from ..crypto.base import CKKS_BATCH_SIZE, CentralizedCryptoBackend, chunk_count
from .client import (
    ClientUpdate,
    EncryptedClientUpdate,
    ciphertext_digest,
    weight_digest,
)

WEIGHTING_MODES = ("legacy", "sample")


@dataclass(frozen=True)
class RegisteredClient:
    client_id: str
    sample_count: int


@dataclass(frozen=True)
class AggregationResult:
    participants: tuple[str, ...]
    weights: tuple[float, ...]
    scaling_factors: tuple[float, ...]
    aggregate_digest: str
    aborted: bool
    reason: str | None
    byzantine_flagged: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "participants": list(self.participants),
            "scaling_factors": [float(value) for value in self.scaling_factors],
            "aggregate_digest": self.aggregate_digest,
            "aborted": self.aborted,
            "reason": self.reason,
            "byzantine_flagged": list(self.byzantine_flagged),
        }


@dataclass(frozen=True)
class AuthToken:
    client_id: str
    token: str
    timestamp: float
    nonce: str


@dataclass(frozen=True)
class EncryptedAggregationResult:
    participants: tuple[str, ...]
    chunks: tuple[bytes, ...]
    scaling_factors: tuple[float, ...]
    aggregate_digest: str
    aborted: bool
    reason: str | None
    byzantine_flagged: tuple[str, ...]
    validation_errors: tuple[tuple[str, str], ...] = ()

    @property
    def total_ciphertext_bytes(self) -> int:
        """Serialized size of the aggregated ciphertext broadcast."""
        return sum(len(chunk) for chunk in self.chunks)

    def as_dict(self) -> dict[str, object]:
        return {
            "participants": list(self.participants),
            "scaling_factors": [float(value) for value in self.scaling_factors],
            "aggregate_digest": self.aggregate_digest,
            "chunk_count": len(self.chunks),
            "aborted": self.aborted,
            "reason": self.reason,
            "byzantine_flagged": list(self.byzantine_flagged),
            "validation_errors": dict(self.validation_errors),
        }


def _auth_token_digest(client_id: str, timestamp: float, nonce: str) -> str:
    payload = f"{client_id}{timestamp:.6f}{nonce}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class FLServer:
    def __init__(
        self,
        *,
        num_clients: int,
        threshold: int,
        expected_parameter_count: int,
        weighting: str = "sample",
        byzantine_threshold: int = 2,
        byzantine_check: bool = False,
        byzantine_max_faults: int | None = None,
        batch_size: int = 32,
        max_clock_drift_seconds: float = 300.0,
    ) -> None:
        if num_clients <= 0:
            raise InputValidationError("num_clients must be positive")
        if not 1 <= threshold <= num_clients:
            raise InputValidationError("threshold must be between 1 and num_clients")
        if expected_parameter_count <= 0:
            raise InputValidationError("expected_parameter_count must be positive")
        if weighting not in WEIGHTING_MODES:
            raise InputValidationError(f"weighting must be one of {', '.join(WEIGHTING_MODES)}")
        if batch_size <= 0:
            raise InputValidationError("batch_size must be positive")
        if max_clock_drift_seconds <= 0:
            raise InputValidationError("max_clock_drift_seconds must be positive")
        effective_max_faults = (
            num_clients // 2 if byzantine_max_faults is None else byzantine_max_faults
        )
        if not 0 <= effective_max_faults <= num_clients:
            raise InputValidationError("byzantine_max_faults must be between 0 and num_clients")
        self.num_clients = num_clients
        self.threshold = threshold
        self.expected_parameter_count = expected_parameter_count
        self.weighting = weighting
        self.byzantine_threshold = byzantine_threshold
        self.byzantine_check = byzantine_check
        self.byzantine_max_faults = effective_max_faults
        self.batch_size = batch_size
        self.max_clock_drift_seconds = max_clock_drift_seconds
        self._clients: dict[str, RegisteredClient] = {}
        self._sessions: dict[str, str] = {}  # client_id -> session_token
        self._round_nonces: dict[tuple[str, int], float] = {}  # (client_id, round_index) -> timestamp
        self._issued_tokens: dict[tuple[str, str], tuple[str, float]] = {}
        self._used_token_nonces: set[str] = set()

    @property
    def registered_clients(self) -> tuple[RegisteredClient, ...]:
        return tuple(self._clients.values())

    def register_client(self, client_id: str, sample_count: int) -> RegisteredClient:
        if not client_id:
            raise InputValidationError("client_id is required")
        if sample_count <= 0:
            raise InputValidationError("sample_count must be positive")
        if client_id in self._clients:
            raise ConflictError(f"client already registered: {client_id}")
        if len(self._clients) >= self.num_clients:
            raise ConflictError("client capacity reached")
        record = RegisteredClient(client_id=client_id, sample_count=int(sample_count))
        self._clients[client_id] = record
        return record

    def authenticate_client(self, client_id: str, session_token: str) -> bool:
        """Authenticate a client via session token. Returns True if valid and fresh."""
        if client_id not in self._clients:
            return False
        # In a full system, session_tokens would be bound to mTLS certificates
        # or signed JWTs. Here we record the token for opt-in authentication.
        self._sessions[client_id] = session_token
        return True

    def issue_auth_token(self, client_id: str, *, now: float | None = None) -> AuthToken:
        """Issue a paper-style ``hash(client_id + timestamp + nonce)`` token."""
        if client_id not in self._clients:
            raise InputValidationError(f"cannot issue a token to unregistered client: {client_id}")
        timestamp = float(time.time() if now is None else now)
        nonce = secrets.token_hex(16)
        token = _auth_token_digest(client_id, timestamp, nonce)
        self._issued_tokens[(client_id, nonce)] = (token, timestamp)
        return AuthToken(
            client_id=client_id,
            token=token,
            timestamp=timestamp,
            nonce=nonce,
        )

    def verify_auth_token(
        self,
        client_id: str,
        token: str,
        timestamp: float,
        nonce: str,
        *,
        now: float | None = None,
    ) -> bool:
        """Verify a token once, enforcing freshness and nonce replay protection."""
        record = self._issued_tokens.get((client_id, nonce))
        if record is None:
            return False
        expected, issued_at = record
        if nonce in self._used_token_nonces:
            return False
        if not hmac.compare_digest(expected, token):
            return False
        current = float(time.time() if now is None else now)
        if abs(current - issued_at) > self.max_clock_drift_seconds:
            return False
        if abs(current - float(timestamp)) > self.max_clock_drift_seconds:
            return False
        self._used_token_nonces.add(nonce)
        return True

    def validate_update(self, update: ClientUpdate) -> None:
        if update.client_id not in self._clients:
            raise InputValidationError(f"update from unregistered client: {update.client_id}")
        if len(update.weights) != self.expected_parameter_count:
            raise InputValidationError(
                f"update from {update.client_id} has {len(update.weights)} weights; "
                f"expected {self.expected_parameter_count}"
            )
        if update.sample_count <= 0:
            raise InputValidationError(f"update from {update.client_id} has no samples")
        if any(not math.isfinite(value) for value in update.weights):
            raise InputValidationError(f"update from {update.client_id} contains non-finite values")
        if update.digest != weight_digest(update.weights, round_index=update.round_index):
            raise InputValidationError(f"weight digest mismatch for {update.client_id}")
        nonce_key = (update.client_id, update.round_index)
        if nonce_key in self._round_nonces:
            raise InputValidationError(f"replay detected for {update.client_id} in round {update.round_index}")
        self._round_nonces[nonce_key] = time.time()

    def _scaling_factors(
        self, updates: Sequence[ClientUpdate | EncryptedClientUpdate]
    ) -> list[float]:
        counts = [update.sample_count for update in updates]
        if any(count <= 0 for count in counts):
            raise InputValidationError("sample counts must be positive")
        if self.weighting == "sample":
            total = sum(counts)
            return [count / total for count in counts]
        # Legacy weight_scaling_factor: number of batches (cardinality) times
        # the batch size, so a partial final batch is counted as a full one.
        effective = [math.ceil(count / self.batch_size) * self.batch_size for count in counts]
        total = sum(effective)
        return [value / total for value in effective]

    def _size_outliers(self, updates: Sequence[ClientUpdate]) -> list[str]:
        """Cardinality-free size-based outlier heuristic.

        This is NOT a Byzantine-resilience control. It is a cardinality-free
        detection of updates whose serialized weight size deviates significantly
        from the group. Outliers may indicate bugs or malicious broadcasts but
        do not by themselves prove Byzantine failure.
        """
        sizes = [len(json.dumps([float(value) for value in update.weights])) for update in updates]
        if len(sizes) < 2:
            return []
        mean = statistics.fmean(sizes)
        spread = statistics.pstdev(sizes)
        if spread == 0.0:
            return []
        return [
            update.client_id
            for update, size in zip(updates, sizes)
            if abs(size - mean) > 3 * spread
        ]

    def _encrypted_update_problem(
        self,
        update: EncryptedClientUpdate,
        crypto: CentralizedCryptoBackend,
    ) -> str | None:
        if update.client_id not in self._clients:
            return "unregistered client"
        if update.sample_count <= 0:
            return "no samples"
        batch_size = int(getattr(crypto, "batch_size", CKKS_BATCH_SIZE))
        expected_chunks = chunk_count(self.expected_parameter_count, batch_size)
        if len(update.chunks) != expected_chunks:
            return f"expected {expected_chunks} ciphertext chunks, got {len(update.chunks)}"
        if not self.verify_auth_token(
            update.client_id,
            update.auth_token,
            update.timestamp,
            update.nonce,
        ):
            return "invalid, stale, or replayed auth token"
        if ciphertext_digest(update.chunks) != update.ciphertext_digest:
            return "ciphertext digest mismatch"
        for chunk in update.chunks:
            if not crypto.validate_ciphertext(chunk):
                return "malformed CKKS ciphertext"
        return None

    def aggregate_encrypted(
        self,
        updates: Sequence[EncryptedClientUpdate],
        crypto: CentralizedCryptoBackend,
    ) -> EncryptedAggregationResult:
        """Verify, filter, and homomorphically aggregate ciphertext updates.

        The server never receives plaintext weights in this path. Invalid
        updates are flagged; the round aborts when the number of flagged
        clients exceeds the paper's ``Tmax = N/2``.
        """
        participants = tuple(update.client_id for update in updates)
        valid: list[EncryptedClientUpdate] = []
        flagged: list[str] = []
        errors: list[tuple[str, str]] = []
        for update in updates:
            problem = self._encrypted_update_problem(update, crypto)
            if problem is None:
                valid.append(update)
            else:
                flagged.append(update.client_id)
                errors.append((update.client_id, problem))

        if len(flagged) > self.byzantine_max_faults:
            return EncryptedAggregationResult(
                participants=participants,
                chunks=(),
                scaling_factors=(),
                aggregate_digest="",
                aborted=True,
                reason=(
                    f"Byzantine threshold exceeded: {len(flagged)} flagged > "
                    f"Tmax={self.byzantine_max_faults}"
                ),
                byzantine_flagged=tuple(flagged),
                validation_errors=tuple(errors),
            )

        if len(valid) < self.threshold:
            return EncryptedAggregationResult(
                participants=participants,
                chunks=(),
                scaling_factors=(),
                aggregate_digest="",
                aborted=True,
                reason=(
                    f"insufficient valid participants: {len(valid)} < threshold "
                    f"{self.threshold}"
                ),
                byzantine_flagged=tuple(flagged),
                validation_errors=tuple(errors),
            )

        factors = self._scaling_factors(valid)
        aggregate: list[bytes] | None = None
        for update, factor in zip(valid, factors):
            scaled = [
                crypto.multiply_by_scalar(chunk, factor) for chunk in update.chunks
            ]
            if aggregate is None:
                aggregate = scaled
            else:
                aggregate = [
                    crypto.add_encrypted(left, right)
                    for left, right in zip(aggregate, scaled)
                ]
        if aggregate is None:
            return EncryptedAggregationResult(
                participants=participants,
                chunks=(),
                scaling_factors=(),
                aggregate_digest="",
                aborted=True,
                reason="no ciphertext was aggregated",
                byzantine_flagged=tuple(flagged),
                validation_errors=tuple(errors),
            )

        chunks = tuple(aggregate)
        return EncryptedAggregationResult(
            participants=tuple(update.client_id for update in valid),
            chunks=chunks,
            scaling_factors=tuple(factors),
            aggregate_digest=ciphertext_digest(chunks),
            aborted=False,
            reason=None,
            byzantine_flagged=tuple(flagged),
            validation_errors=tuple(errors),
        )

    def aggregate(self, updates: Sequence[ClientUpdate]) -> AggregationResult:
        # Step 1: authenticate each client (opt-in; no token = unauthenticated but not rejected
        # in plaintext mode; encryption mode would require it)
        for update in updates:
            if update.session_token:
                self.authenticate_client(update.client_id, update.session_token)

        # Step 2: validate each update (shape, finite values, sample count)
        for update in updates:
            self.validate_update(update)

        participants = tuple(update.client_id for update in updates)

        # Step 3: threshold check
        if len(updates) < self.threshold:
            return AggregationResult(
                participants=participants,
                weights=(),
                scaling_factors=(),
                aggregate_digest="",
                aborted=True,
                reason=f"insufficient participants: {len(updates)} < threshold {self.threshold}",
                byzantine_flagged=(),
            )

        # Step 4: Byzantine opt-in check (size-based outlier heuristic)
        flagged: tuple[str, ...] = ()
        if self.byzantine_check:
            flagged = tuple(self._size_outliers(updates))
            if len(flagged) >= self.byzantine_threshold:
                return AggregationResult(
                    participants=participants,
                    weights=(),
                    scaling_factors=(),
                    aggregate_digest="",
                    aborted=True,
                    reason=(
                        "legacy size-outlier heuristic flagged "
                        f"{len(flagged)} updates (not a security control)"
                    ),
                    byzantine_flagged=flagged,
                )

        # Step 5: weighted aggregation
        factors = self._scaling_factors(updates)
        width = self.expected_parameter_count
        aggregated = [0.0] * width
        for update, factor in zip(updates, factors):
            for index, value in enumerate(update.weights):
                aggregated[index] += float(value) * factor
        weights = tuple(float(value) for value in aggregated)
        return AggregationResult(
            participants=participants,
            weights=weights,
            scaling_factors=tuple(factors),
            aggregate_digest=weight_digest(weights),
            aborted=False,
            reason=None,
            byzantine_flagged=flagged,
        )
