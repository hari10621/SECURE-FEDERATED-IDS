"""Deterministic simulated federated core (plaintext and TenSEAL modes)."""

from .backends import ReferenceLinearBackend, TrainingBackend
from .client import (
    BroadcastPackage,
    ClientUpdate,
    EncryptedClientUpdate,
    SimulatedClient,
    ciphertext_digest,
    delta_weights,
    encrypted_model_hash,
    make_broadcast,
    plaintext_update_size,
    verify_broadcast,
    weight_digest,
)
from .round import (
    EncryptedFederatedHarness,
    FederatedAborted,
    FederatedConfig,
    FederatedHarness,
    client_id_for,
    derive_client_seed,
    partition_training_indices,
)
from .server import (
    AggregationResult,
    AuthToken,
    EncryptedAggregationResult,
    FLServer,
    RegisteredClient,
)

__all__ = [
    "AggregationResult",
    "AuthToken",
    "BroadcastPackage",
    "ClientUpdate",
    "EncryptedAggregationResult",
    "EncryptedClientUpdate",
    "EncryptedFederatedHarness",
    "FLServer",
    "FederatedAborted",
    "FederatedConfig",
    "FederatedHarness",
    "ReferenceLinearBackend",
    "RegisteredClient",
    "SimulatedClient",
    "TrainingBackend",
    "ciphertext_digest",
    "client_id_for",
    "delta_weights",
    "derive_client_seed",
    "encrypted_model_hash",
    "make_broadcast",
    "partition_training_indices",
    "plaintext_update_size",
    "verify_broadcast",
    "weight_digest",
]
