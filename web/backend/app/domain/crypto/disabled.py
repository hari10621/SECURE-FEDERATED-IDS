"""Fail-closed crypto backend.

Every operation raises. No ciphertext, key, or partial decryption is produced.
"""

from __future__ import annotations

from .base import CryptoBackend, CryptoStatus, CryptoUnavailable

REASON = (
    "Native CKKS backend is not installed or verified. Encrypted aggregation "
    "and threshold decryption are disabled."
)


class DisabledCryptoBackend(CryptoBackend):
    backend = "disabled"

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
        raise CryptoUnavailable("encryption is unavailable; no ciphertext was produced")

    def add_encrypted(self, left: bytes, right: bytes) -> bytes:
        raise CryptoUnavailable("homomorphic addition is unavailable")

    def multiply_by_scalar(self, ciphertext: bytes, scalar: float) -> bytes:
        raise CryptoUnavailable("homomorphic scaling is unavailable")

    def threshold_decrypt(self, chunks: list[bytes], party_ids: list[int]) -> list[float]:
        raise CryptoUnavailable("threshold decryption is unavailable; no plaintext was produced")
