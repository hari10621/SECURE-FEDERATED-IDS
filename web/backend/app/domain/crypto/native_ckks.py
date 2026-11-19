"""Placeholder for the historical ``true_threshold_ckks`` extension.

The original Linux/CPython 3.8 shared object is not present and its source is
missing. This class intentionally does not import or probe the extension: doing
so would risk claiming availability without the Phase 2 verification gate
(known-answer tests, DKG sequence, threshold failure cases). It always fails
closed until a verified backend is supplied elsewhere.
"""

from __future__ import annotations

from .base import CryptoBackend, CryptoStatus, CryptoUnavailable

REASON = (
    "Native CKKS extension is not installed, and its source and exact OpenFHE "
    "version are unavailable. The verification gate has not been run."
)


class NativeCKKSBackend(CryptoBackend):
    backend = "native_ckks"

    def status(self) -> CryptoStatus:
        return CryptoStatus(
            available=False,
            mode="unavailable",
            backend=self.backend,
            reason=REASON,
            encryption_claimed=False,
        )

    def initialize(self, params: dict[str, int]) -> None:
        raise CryptoUnavailable(REASON)

    def encrypt_vector(self, values: list[float]) -> list[bytes]:
        raise CryptoUnavailable(REASON)

    def add_encrypted(self, left: bytes, right: bytes) -> bytes:
        raise CryptoUnavailable(REASON)

    def multiply_by_scalar(self, ciphertext: bytes, scalar: float) -> bytes:
        raise CryptoUnavailable(REASON)

    def threshold_decrypt(self, chunks: list[bytes], party_ids: list[int]) -> list[float]:
        raise CryptoUnavailable(REASON)
