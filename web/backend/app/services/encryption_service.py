"""Fail-closed encryption boundary.

The native ``true_threshold_ckks`` extension is Linux/CPython 3.8-only and is
not present in this workspace. This service must never manufacture ciphertext,
metrics, or a fake "encrypted" status. It can only report unavailable and reject
cryptographic operations until a verified backend is installed.
"""

from __future__ import annotations

from typing import Any

from ..errors import UnavailableError


class EncryptionService:
    backend = "native_ckks"

    def is_available(self) -> bool:
        return False

    def status(self) -> dict[str, Any]:
        return {
            "available": False,
            "backend": self.backend,
            "reason": (
                "Native CKKS backend is not installed or verified. "
                "Encrypted aggregation and threshold decryption are disabled."
            ),
        }

    def encrypt(self, _values: list[float]) -> None:
        raise UnavailableError("encryption is unavailable; no ciphertext was produced")

    def decrypt(self, _ciphertext: Any) -> None:
        raise UnavailableError("decryption is unavailable; no plaintext was produced")
