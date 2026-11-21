"""TenSEAL-backed CKKS with a centralized Trusted Authority.

This implements the paper's protocol: an offline Trusted Authority creates one
CKKS keypair, clients encrypt their weight deltas with the public context, the
server homomorphically aggregates ciphertexts, and clients decrypt the aggregate
with the secret context. The server-side backend never holds the secret key.

TenSEAL is an optional dependency. When it is not installed every operation
fails closed and ``status().available`` is ``False``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from .base import (
    CKKS_BATCH_SIZE,
    CKKS_MULT_DEPTH,
    CKKS_RING_DIM,
    CKKS_SCALE_BITS,
    CryptoStatus,
    CryptoUnavailable,
    default_ckks_params,
)

try:  # pragma: no cover - exercised by availability tests
    import tenseal as ts
except Exception as exc:  # pragma: no cover - import guard
    ts = None
    _TENSEAL_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
else:
    _TENSEAL_IMPORT_ERROR = ""

# Paper section: Q = [60, 40, 40, 60], scale = 2^40, depth = 2.
CKKS_COEFF_MOD_BIT_SIZES = (60, 40, 40, 60)

TENSEAL_REASON = (
    "TenSEAL is not installed. Install requirements-crypto.txt to enable the "
    "centralized CKKS backend."
    if ts is None
    else "TenSEAL is installed."
)


def tenseal_available() -> bool:
    return ts is not None


def _require_tenseal() -> Any:
    if ts is None:
        raise CryptoUnavailable(
            "TenSEAL is unavailable",
            details={"import_error": _TENSEAL_IMPORT_ERROR},
        )
    return ts


@dataclass(frozen=True)
class KeyMaterial:
    """TA output. ``secret_context`` must only reach clients."""

    public_context: bytes
    secret_context: bytes
    context_hash: str
    params: dict[str, int]

    def public_info(self) -> dict[str, Any]:
        return {
            "context_hash": self.context_hash,
            "params": dict(self.params),
            "secret_exported": False,
        }


class TrustedAuthority:
    """Offline key authority.

    ``generate`` creates the shared keypair. ``decommission`` drops the
    authority's own references; callers are responsible for delivering the
    secret context to clients and never to the aggregation server.
    """

    def __init__(self, params: dict[str, int] | None = None) -> None:
        self.params = dict(params or default_ckks_params(parties=0, threshold=0))
        self._material: KeyMaterial | None = None
        self._decommissioned = False

    @property
    def material(self) -> KeyMaterial | None:
        return self._material

    def generate(self) -> KeyMaterial:
        if self._decommissioned:
            raise CryptoUnavailable("Trusted Authority has been decommissioned")
        lib = _require_tenseal()
        ring_dim = int(self.params.get("ring_dim", CKKS_RING_DIM))
        scale_bits = int(self.params.get("scale_bits", CKKS_SCALE_BITS))
        context = lib.context(
            lib.SCHEME_TYPE.CKKS,
            poly_modulus_degree=ring_dim,
            coeff_mod_bit_sizes=list(CKKS_COEFF_MOD_BIT_SIZES),
        )
        context.global_scale = 2**scale_bits
        context.generate_galois_keys()
        public_context = context.serialize(save_secret_key=False)
        secret_context = context.serialize(save_secret_key=True)
        material = KeyMaterial(
            public_context=public_context,
            secret_context=secret_context,
            context_hash=hashlib.sha256(public_context).hexdigest(),
            params=dict(self.params),
        )
        self._material = material
        return material

    def decommission(self) -> None:
        self._material = None
        self._decommissioned = True


class TensealCKKSBackend:
    """TenSEAL CKKS backend.

    Pass ``public_context`` for the server side and add ``secret_context`` only
    for the client-side keyring used to decrypt the aggregate.
    """

    backend = "tenseal_ckks"

    def __init__(
        self,
        *,
        public_context: bytes | None = None,
        secret_context: bytes | None = None,
        batch_size: int = CKKS_BATCH_SIZE,
        ring_dim: int = CKKS_RING_DIM,
        mult_depth: int = CKKS_MULT_DEPTH,
        scale_bits: int = CKKS_SCALE_BITS,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self.batch_size = int(batch_size)
        self.ring_dim = int(ring_dim)
        self.mult_depth = int(mult_depth)
        self.scale_bits = int(scale_bits)
        self._public_ctx: Any | None = None
        self._secret_ctx: Any | None = None
        if ts is not None and public_context is not None:
            self._public_ctx = ts.context_from(public_context)
        if ts is not None and secret_context is not None:
            self._secret_ctx = ts.context_from(secret_context)

    @classmethod
    def from_material(
        cls,
        material: KeyMaterial,
        *,
        include_secret: bool,
    ) -> "TensealCKKSBackend":
        return cls(
            public_context=material.public_context,
            secret_context=material.secret_context if include_secret else None,
            batch_size=int(material.params.get("batch_size", CKKS_BATCH_SIZE)),
            ring_dim=int(material.params.get("ring_dim", CKKS_RING_DIM)),
            mult_depth=int(material.params.get("mult_depth", CKKS_MULT_DEPTH)),
            scale_bits=int(material.params.get("scale_bits", CKKS_SCALE_BITS)),
        )

    @property
    def has_secret_key(self) -> bool:
        return self._secret_ctx is not None

    def params(self) -> dict[str, int]:
        return {
            "ring_dim": self.ring_dim,
            "batch_size": self.batch_size,
            "mult_depth": self.mult_depth,
            "scale_bits": self.scale_bits,
        }

    def status(self) -> CryptoStatus:
        if ts is None:
            return CryptoStatus(
                available=False,
                mode="unavailable",
                backend=self.backend,
                reason=TENSEAL_REASON,
                encryption_claimed=False,
            )
        if self._public_ctx is None:
            return CryptoStatus(
                available=True,
                mode="centralized_ckks",
                backend=self.backend,
                reason=(
                    "TenSEAL is installed; no key material is loaded. "
                    "Run the Trusted Authority key ceremony for this run."
                ),
                encryption_claimed=False,
            )
        return CryptoStatus(
            available=True,
            mode="centralized_ckks",
            backend=self.backend,
            reason=(
                "TenSEAL CKKS key material is loaded. "
                + (
                    "The client keyring holds the secret context."
                    if self._secret_ctx is not None
                    else "This server-side context holds only the public key."
                )
            ),
            encryption_claimed=self._secret_ctx is not None,
        )

    def initialize(self, params: dict[str, int]) -> None:
        """Run an in-process TA ceremony and load the resulting keypair."""
        material = TrustedAuthority(params).generate()
        lib = _require_tenseal()
        self.batch_size = int(material.params.get("batch_size", self.batch_size))
        self.ring_dim = int(material.params.get("ring_dim", self.ring_dim))
        self.mult_depth = int(material.params.get("mult_depth", self.mult_depth))
        self.scale_bits = int(material.params.get("scale_bits", self.scale_bits))
        self._public_ctx = lib.context_from(material.public_context)
        self._secret_ctx = lib.context_from(material.secret_context)

    def _require_public(self) -> Any:
        if ts is None:
            raise CryptoUnavailable(TENSEAL_REASON)
        if self._public_ctx is None:
            raise CryptoUnavailable("CKKS public context is not loaded")
        return self._public_ctx

    def encrypt_vector(self, values: list[float]) -> list[bytes]:
        context = self._require_public()
        if not values:
            raise ValueError("cannot encrypt an empty vector")
        chunks: list[bytes] = []
        for start in range(0, len(values), self.batch_size):
            chunk = [float(value) for value in values[start : start + self.batch_size]]
            if len(chunk) < self.batch_size:
                chunk = chunk + [0.0] * (self.batch_size - len(chunk))
            chunks.append(ts.ckks_vector(context, chunk).serialize())
        return chunks

    def add_encrypted(self, left: bytes, right: bytes) -> bytes:
        context = self._require_public()
        left_vec = ts.ckks_vector_from(context, left)
        right_vec = ts.ckks_vector_from(context, right)
        return (left_vec + right_vec).serialize()

    def multiply_by_scalar(self, ciphertext: bytes, scalar: float) -> bytes:
        context = self._require_public()
        vector = ts.ckks_vector_from(context, ciphertext)
        return (vector * float(scalar)).serialize()

    def validate_ciphertext(self, ciphertext: bytes) -> bool:
        if ts is None or self._public_ctx is None or not ciphertext:
            return False
        try:
            ts.ckks_vector_from(self._public_ctx, ciphertext)
        except Exception:
            return False
        return True

    def decrypt_aggregate(self, chunks: list[bytes], expected_count: int) -> list[float]:
        if ts is None:
            raise CryptoUnavailable(TENSEAL_REASON)
        if self._secret_ctx is None:
            raise CryptoUnavailable(
                "this backend does not hold the CKKS secret key; decryption is "
                "a client-side operation"
            )
        if expected_count <= 0:
            raise ValueError("expected_count must be positive")
        values: list[float] = []
        for chunk in chunks:
            values.extend(float(value) for value in ts.ckks_vector_from(self._secret_ctx, chunk).decrypt())
        if len(values) < expected_count:
            raise CryptoUnavailable(
                f"decrypted {len(values)} values but expected {expected_count}"
            )
        return values[:expected_count]

    def threshold_decrypt(
        self, chunks: list[bytes], party_ids: list[int]
    ) -> list[float]:
        raise CryptoUnavailable(
            "the centralized Trusted Authority backend does not implement "
            "threshold decryption"
        )
