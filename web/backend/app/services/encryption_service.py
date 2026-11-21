"""Encryption boundary.

The default configuration is fail-closed: no CKKS backend is loaded and every
cryptographic operation is rejected. When ``SECUREFED_ENABLE_CKKS`` is set, the
TenSEAL backend becomes available and the Trusted Authority ceremony can issue
per-run key material.

The secret context is only ever handed to a client-side keyring. The aggregation
server receives a public-context-only backend.
"""

from __future__ import annotations

from typing import Any

from ..config import Settings
from ..domain.crypto import (
    CentralizedCryptoBackend,
    DisabledCryptoBackend,
    KeyMaterial,
    NativeCKKSBackend,
    TensealCKKSBackend,
    TrustedAuthority,
    default_ckks_params,
)
from ..errors import UnavailableError


class EncryptionService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings
        self._backend = self._select_backend()

    def _select_backend(self) -> Any:
        if self.settings is None or not self.settings.enable_ckks:
            return DisabledCryptoBackend()
        if self.settings.ckks_backend == "native":
            return NativeCKKSBackend()
        return TensealCKKSBackend()

    @property
    def backend(self) -> str:
        return str(getattr(self._backend, "backend", "disabled"))

    def is_available(self) -> bool:
        return bool(self._backend.status().available)

    def status(self) -> dict[str, Any]:
        status = self._backend.status()
        payload = status.as_dict()
        if isinstance(self._backend, TensealCKKSBackend):
            payload["params"] = self._backend.params()
        else:
            payload["params"] = default_ckks_params(parties=0, threshold=0)
        payload["key_ceremony"] = "per_run" if payload["available"] else "disabled"
        payload["secret_key_location"] = "client_keyring_only"
        return payload

    def generate_key_material(
        self, *, parties: int = 0, threshold: int = 0
    ) -> KeyMaterial:
        if not self.is_available():
            raise UnavailableError(
                "CKKS key generation is unavailable",
                details={"crypto": self.status()},
            )
        authority = TrustedAuthority(
            default_ckks_params(parties=parties, threshold=threshold)
        )
        material = authority.generate()
        authority.decommission()
        return material

    def server_backend(self, material: KeyMaterial) -> CentralizedCryptoBackend:
        """Public-context-only backend for the aggregation server."""
        return TensealCKKSBackend.from_material(material, include_secret=False)

    def client_keyring(self, material: KeyMaterial) -> CentralizedCryptoBackend:
        """Client-side backend that holds the secret context."""
        return TensealCKKSBackend.from_material(material, include_secret=True)

    def encrypt(self, values: list[float]) -> list[bytes]:
        if not self.is_available():
            raise UnavailableError("encryption is unavailable; no ciphertext was produced")
        if not isinstance(self._backend, TensealCKKSBackend):
            raise UnavailableError("encryption is unavailable; no ciphertext was produced")
        return self._backend.encrypt_vector(values)

    def decrypt(self, _ciphertext: Any) -> None:
        raise UnavailableError(
            "decryption is a client-side keyring operation and is never exposed "
            "through the encryption service"
        )
