"""Deterministic simulated federated core (plaintext and TenSEAL modes)."""

from .backends import ReferenceLinearBackend, TrainingBackend
from .client import (
    ClientUpdate,
    EncryptedClientUpdate,
    SimulatedClient,
    ciphertext_digest,
    delta_weights,
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
    "partition_training_indices",
    "weight_digest",
]
