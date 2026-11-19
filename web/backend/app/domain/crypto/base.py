"""Cryptographic boundary for the federated core.

The federated harness may only use a backend whose status is verified. The
native CKKS extension is absent, so every real backend here reports
``available: false``. A backend must never return placeholder or fabricated
ciphertext; callers have to treat unavailability as fail-closed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Protocol, runtime_checkable

from ...errors import UnavailableError

CKKS_RING_DIM = 8192
CKKS_BATCH_SIZE = 4096
CKKS_MULT_DEPTH = 2
CKKS_SCALE_BITS = 40


def default_ckks_params(*, parties: int, threshold: int) -> dict[str, int]:
    """The parameter block used by the original research scripts."""
    return {
        "parties": parties,
        "threshold": threshold,
        "ring_dim": CKKS_RING_DIM,
        "batch_size": CKKS_BATCH_SIZE,
        "mult_depth": CKKS_MULT_DEPTH,
        "scale_bits": CKKS_SCALE_BITS,
    }


@dataclass(frozen=True)
class CryptoStatus:
    available: bool
    mode: str
    backend: str
    reason: str
    encryption_claimed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class CryptoUnavailable(UnavailableError):
    """Raised when a cryptographic operation cannot be performed safely."""

    code = "crypto_unavailable"


@runtime_checkable
class CryptoBackend(Protocol):
    """Minimal threshold-CKKS surface used by the federated core.

    Implementations operate on opaque ciphertext bytes. Nothing in this
    protocol permits plaintext to be labelled as encrypted.
    """

    def status(self) -> CryptoStatus: ...

    def initialize(self, params: dict[str, int]) -> None: ...

    def encrypt_vector(self, values: list[float]) -> list[bytes]: ...

    def add_encrypted(self, left: bytes, right: bytes) -> bytes: ...

    def multiply_by_scalar(self, ciphertext: bytes, scalar: float) -> bytes: ...

    def threshold_decrypt(
        self, chunks: list[bytes], party_ids: list[int]
    ) -> list[float]: ...
