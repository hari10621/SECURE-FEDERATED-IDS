"""Fail-closed cryptographic interfaces for the federated core."""

from .base import (
    CKKS_BATCH_SIZE,
    CKKS_MULT_DEPTH,
    CKKS_RING_DIM,
    CKKS_SCALE_BITS,
    CryptoBackend,
    CryptoStatus,
    CryptoUnavailable,
    default_ckks_params,
)
from .disabled import DisabledCryptoBackend
from .native_ckks import NativeCKKSBackend
from .plaintext import PlaintextSimulationBackend

__all__ = [
    "CKKS_BATCH_SIZE",
    "CKKS_MULT_DEPTH",
    "CKKS_RING_DIM",
    "CKKS_SCALE_BITS",
    "CryptoBackend",
    "CryptoStatus",
    "CryptoUnavailable",
    "DisabledCryptoBackend",
    "NativeCKKSBackend",
    "PlaintextSimulationBackend",
    "default_ckks_params",
]
