"""Deterministic simulated federated core (plaintext only)."""

from .backends import ReferenceLinearBackend, TrainingBackend
from .client import ClientUpdate, SimulatedClient, weight_digest
from .round import (
    FederatedAborted,
    FederatedConfig,
    FederatedHarness,
    client_id_for,
    derive_client_seed,
    partition_training_indices,
)
from .server import AggregationResult, FLServer, RegisteredClient

__all__ = [
    "AggregationResult",
    "ClientUpdate",
    "FLServer",
    "FederatedAborted",
    "FederatedConfig",
    "FederatedHarness",
    "ReferenceLinearBackend",
    "RegisteredClient",
    "SimulatedClient",
    "TrainingBackend",
    "client_id_for",
    "derive_client_seed",
    "partition_training_indices",
    "weight_digest",
]
