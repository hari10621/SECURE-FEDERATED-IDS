"""In-process federated aggregation over plaintext simulation updates.

The server validates shapes and weights, applies one of two weighting schemes,
and returns a deterministic aggregate. The optional size-based outlier check is
a reproduction of the legacy heuristic, not a security control.
"""

from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass
from typing import Sequence

from ...errors import ConflictError, InputValidationError
from .client import ClientUpdate, weight_digest

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
        batch_size: int = 32,
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
        self.num_clients = num_clients
        self.threshold = threshold
        self.expected_parameter_count = expected_parameter_count
        self.weighting = weighting
        self.byzantine_threshold = byzantine_threshold
        self.byzantine_check = byzantine_check
        self.batch_size = batch_size
        self._clients: dict[str, RegisteredClient] = {}

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

    def _scaling_factors(self, updates: Sequence[ClientUpdate]) -> list[float]:
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

    def aggregate(self, updates: Sequence[ClientUpdate]) -> AggregationResult:
        for update in updates:
            self.validate_update(update)
        participants = tuple(update.client_id for update in updates)

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
