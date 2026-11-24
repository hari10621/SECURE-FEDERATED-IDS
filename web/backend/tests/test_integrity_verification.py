from __future__ import annotations

import json

import pytest

from app.domain.federated import (
    BroadcastPackage,
    EncryptedClientUpdate,
    SimulatedClient,
    encrypted_model_hash,
    make_broadcast,
    verify_broadcast,
)
from app.domain.federated.backends import ReferenceLinearBackend
from app.errors import IntegrityError


class _PlaintextCrypto:
    """Minimal crypto double: one deterministic ciphertext chunk per vector."""

    def encrypt_vector(self, values):
        return [json.dumps([float(value) for value in values]).encode("utf-8")]


def _client() -> SimulatedClient:
    rows = [
        [((index * (position + 3)) % 17) / 10.0 for position in range(4)]
        for index in range(20)
    ]
    labels = [index % 2 for index in range(20)]
    return SimulatedClient(client_id="client-1", rows=rows, labels=labels, seed=7)


def _train(client: SimulatedClient, *, broadcast=None) -> EncryptedClientUpdate:
    backend = ReferenceLinearBackend()
    return client.train_encrypted(
        backend.initial_weights(4),
        backend,
        _PlaintextCrypto(),
        round_index=0,
        epochs=1,
        batch_size=4,
        learning_rate=0.1,
        auth_token="token",
        timestamp=0.0,
        nonce="nonce",
        broadcast=broadcast,
    )


def test_broadcast_hash_round_trip_matches_sha256():
    chunks = [b"encrypted-model-part-one", b"part-two"]
    package = make_broadcast(round_index=3, chunks=chunks)
    assert package.hash == encrypted_model_hash(chunks)
    assert verify_broadcast(package) == package.hash


def test_client_accepts_verified_broadcast_and_records_hash():
    package = make_broadcast(0, [b"global-model"])
    update = _train(_client(), broadcast=package)
    assert update.broadcast_hash == package.hash
    assert update.as_dict()["broadcast_hash"] == package.hash


def test_client_rejects_tampered_broadcast():
    package = make_broadcast(0, [b"global-model"])
    tampered = BroadcastPackage(
        round_index=package.round_index,
        chunks=(b"tampered-model",),
        hash=package.hash,
    )
    with pytest.raises(IntegrityError, match="hash mismatch"):
        _train(_client(), broadcast=tampered)


def test_encrypted_harness_verifies_broadcast_before_decryption():
    pytest.importorskip("tenseal")
    from app.domain.crypto import TensealCKKSBackend, TrustedAuthority, default_ckks_params
    from app.domain.dataset import preprocess
    from app.domain.federated import EncryptedFederatedHarness, FederatedConfig

    rows = [
        [((index * (position + 3)) % 17) / 10.0 for position in range(4)]
        for index in range(80)
    ]
    labels = [index % 2 for index in range(80)]
    prepared = preprocess(
        rows,
        labels,
        feature_names=[f"f{index}" for index in range(4)],
        mode="clean",
    )

    authority = TrustedAuthority(default_ckks_params(parties=4, threshold=2))
    material = authority.generate()
    authority.decommission()
    server = TensealCKKSBackend.from_material(material, include_secret=False)
    keyring = TensealCKKSBackend.from_material(material, include_secret=True)

    harness = EncryptedFederatedHarness(
        ReferenceLinearBackend(),
        FederatedConfig(num_clients=4, rounds=1, local_epochs=1, batch_size=8),
        server,
        keyring,
        context_hash=material.context_hash,
    )
    result = harness.run(prepared)
    assert result["integrity"]["algorithm"] == "sha256"
    assert result["integrity"]["broadcast_hash_verified"] is True
    assert result["integrity"]["last_broadcast_hash"]
    record = result["rounds"][0]
    assert record["broadcast_hash_verified"] is True
    assert record["broadcast_hash"] == result["integrity"]["last_broadcast_hash"]
    assert result["rounds"][0]["updates"][0]["broadcast_hash"] == ""

    metrics = result["round_metrics"][0]
    assert metrics["plaintext_update_size_bytes"] > 0
    assert metrics["encrypted_update_size_bytes"] > metrics["plaintext_update_size_bytes"]
    assert metrics["expansion_ratio"] == pytest.approx(
        metrics["encrypted_update_size_bytes"] / metrics["plaintext_update_size_bytes"],
        rel=1e-3,
    )
    assert record["aggregate_ciphertext_bytes"] > 0
