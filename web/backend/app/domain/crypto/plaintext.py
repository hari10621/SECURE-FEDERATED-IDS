"""Explicit plaintext simulation mode.

This backend is not cryptography. It exists so the deterministic round harness
can be exercised and tested locally. It never produces ciphertext, never
reports ``available``, and never sets ``encryption_claimed``.
"""

from __future__ import annotations

from .base import CryptoBackend, CryptoStatus, CryptoUnavailable

REASON = (
    "Plaintext simulation only: no encryption, DKG, or threshold decryption is "
    "performed. Results must not be reported as encrypted federated learning."
)


class PlaintextSimulationBackend(CryptoBackend):
    backend = "plaintext_simulation"

    def status(self) -> CryptoStatus:
        return CryptoStatus(
            available=False,
            mode="plaintext_simulation",
            backend=self.backend,
            reason=REASON,
            encryption_claimed=False,
        )

    def initialize(self, params: dict[str, int]) -> None:
        raise CryptoUnavailable(REASON)

    def encrypt_vector(self, values: list[float]) -> list[bytes]:
        raise CryptoUnavailable("plaintext simulation does not produce ciphertext")

    def add_encrypted(self, left: bytes, right: bytes) -> bytes:
        raise CryptoUnavailable("plaintext simulation does not operate on ciphertext")

    def multiply_by_scalar(self, ciphertext: bytes, scalar: float) -> bytes:
        raise CryptoUnavailable("plaintext simulation does not operate on ciphertext")

    def threshold_decrypt(self, chunks: list[bytes], party_ids: list[int]) -> list[float]:
        raise CryptoUnavailable("plaintext simulation does not perform threshold decryption")
