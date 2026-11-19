from __future__ import annotations

import math

import pytest

from app.domain.crypto import (
    DisabledCryptoBackend,
    NativeCKKSBackend,
    PlaintextSimulationBackend,
)
from app.domain.dataset import preprocess
from app.domain.federated import (
    ClientUpdate,
    FLServer,
    FederatedAborted,
    FederatedConfig,
    FederatedHarness,
    ReferenceLinearBackend,
    client_id_for,
    partition_training_indices,
)
from app.errors import ConflictError, InputValidationError, UnavailableError


def _rows(count: int = 80, features: int = 4) -> tuple[list[list[float]], list[int]]:
    rows = [
        [((index * (position + 3)) % 17) / 10.0 for position in range(features)]
        for index in range(count)
    ]
    labels = [index % 2 for index in range(count)]
    return rows, labels


def _prepared():
    rows, labels = _rows()
    return preprocess(
        rows,
        labels,
        feature_names=[f"f{index}" for index in range(4)],
        mode="clean",
        seed=42,
    )


def _update(client_id: str, weights, count: int, round_index: int = 0) -> ClientUpdate:
    return ClientUpdate(
        client_id=client_id,
        weights=tuple(float(value) for value in weights),
        sample_count=count,
        digest="0" * 64,
        round_index=round_index,
    )


def test_crypto_backends_fail_closed():
    for backend in (DisabledCryptoBackend(), NativeCKKSBackend(), PlaintextSimulationBackend()):
        status = backend.status()
        assert status.available is False
        assert status.encryption_claimed is False
        with pytest.raises(UnavailableError):
            backend.encrypt_vector([1.0, 2.0])
        with pytest.raises(UnavailableError):
            backend.threshold_decrypt([b"not-ciphertext"], [1])
    assert PlaintextSimulationBackend().status().mode == "plaintext_simulation"
    assert DisabledCryptoBackend().status().mode == "unavailable"


def test_partition_matches_legacy_floor_and_drops_remainder():
    labels = [0] * 10
    shards = partition_training_indices(labels, num_clients=4, seed=5)
    assert [len(shard) for shard in shards] == [2, 2, 2, 2]
    combined = [index for shard in shards for index in shard]
    assert len(combined) == 8
    assert len(set(combined)) == 8
    assert shards == partition_training_indices(labels, num_clients=4, seed=5)
    assert shards != partition_training_indices(labels, num_clients=4, seed=6)
    with pytest.raises(InputValidationError):
        partition_training_indices([0, 1], num_clients=4, seed=1)
    with pytest.raises(InputValidationError):
        client_id_for(0)


def test_server_registration_and_update_validation():
    server = FLServer(
        num_clients=2,
        threshold=1,
        expected_parameter_count=3,
        weighting="sample",
    )
    server.register_client("client-1", 4)
    with pytest.raises(ConflictError):
        server.register_client("client-1", 4)
    with pytest.raises(InputValidationError):
        server.validate_update(_update("missing", [0, 0, 0], 1))
    with pytest.raises(InputValidationError):
        server.validate_update(_update("client-1", [0, 0], 1))
    with pytest.raises(InputValidationError):
        server.validate_update(_update("client-1", [0, math.inf, 0], 1))
    server.validate_update(_update("client-1", [0, 0, 0], 4))


def test_sample_weighting_is_exact():
    server = FLServer(
        num_clients=2,
        threshold=1,
        expected_parameter_count=3,
        weighting="sample",
    )
    server.register_client("client-1", 1)
    server.register_client("client-2", 3)
    result = server.aggregate(
        [_update("client-1", [1, 2, 3], 1), _update("client-2", [3, 2, 1], 3)]
    )
    assert result.aborted is False
    assert result.scaling_factors == pytest.approx((0.25, 0.75))
    assert result.weights == pytest.approx((2.5, 2.0, 1.5))
    assert len(result.aggregate_digest) == 64


def test_legacy_weighting_rounds_partial_batches_up():
    server = FLServer(
        num_clients=2,
        threshold=1,
        expected_parameter_count=2,
        weighting="legacy",
        batch_size=32,
    )
    server.register_client("client-1", 33)
    server.register_client("client-2", 31)
    result = server.aggregate(
        [_update("client-1", [1, 1], 33), _update("client-2", [3, 3], 31)]
    )
    assert result.scaling_factors == pytest.approx((64 / 96, 32 / 96))
    assert result.weights == pytest.approx((5 / 3, 5 / 3))


def test_insufficient_participants_aborts():
    server = FLServer(
        num_clients=3,
        threshold=3,
        expected_parameter_count=1,
    )
    for client_id in ("a", "b", "c"):
        server.register_client(client_id, 1)
    result = server.aggregate([_update("a", [1], 1), _update("b", [1], 1)])
    assert result.aborted is True
    assert "insufficient participants" in (result.reason or "")


def test_legacy_byzantine_heuristic_is_opt_in():
    updates = [_update(f"c{index}", [0.0, 0.0], 1) for index in range(11)]
    updates.append(_update("loud", [1e9, 1e9], 1))

    disabled = FLServer(
        num_clients=12,
        threshold=1,
        expected_parameter_count=2,
        byzantine_check=False,
    )
    enabled = FLServer(
        num_clients=12,
        threshold=1,
        expected_parameter_count=2,
        byzantine_check=True,
        byzantine_threshold=1,
    )
    for server in (disabled, enabled):
        for update in updates:
            server.register_client(update.client_id, 1)

    assert disabled.aggregate(updates).aborted is False
    flagged = enabled.aggregate(updates)
    assert flagged.aborted is True
    assert flagged.byzantine_flagged == ("loud",)


def test_harness_is_deterministic_and_labels_plaintext():
    prepared = _prepared()
    config = FederatedConfig(
        num_clients=4,
        rounds=3,
        local_epochs=1,
        batch_size=8,
        learning_rate=0.1,
        seed=7,
    )

    first = FederatedHarness(ReferenceLinearBackend(), config).run(prepared)
    second = FederatedHarness(ReferenceLinearBackend(), config).run(prepared)

    assert first == second
    assert first["mode"] == "plaintext_simulation"
    assert first["encrypted"] is False
    assert first["encryption_claimed"] is False
    assert first["crypto"]["available"] is False
    assert first["parity"] == "unverified"
    assert first["model"]["name"] == "reference_linear"
    assert first["model"]["research_model"] is False
    assert "not a legacy-parity claim" in first["parity_note"] or "No parity claim" in first["parity_note"]
    assert "auc" in first["final_metrics"]
    assert len(first["rounds"]) == 3
    assert first["legacy_differences"]
    assert first["aggregate_digest"] == second["aggregate_digest"]


def test_harness_seed_changes_round_updates():
    prepared = _prepared()
    base = dict(
        num_clients=4,
        rounds=1,
        local_epochs=1,
        batch_size=8,
        learning_rate=0.1,
    )
    first = FederatedHarness(
        ReferenceLinearBackend(), FederatedConfig(seed=7, **base)
    ).run(prepared)
    second = FederatedHarness(
        ReferenceLinearBackend(), FederatedConfig(seed=8, **base)
    ).run(prepared)
    assert first["rounds"][0]["updates"] != second["rounds"][0]["updates"]


def test_harness_requires_encryption_fail_closed():
    prepared = _prepared()
    config = FederatedConfig(num_clients=4, rounds=1, require_encryption=True)
    with pytest.raises(UnavailableError):
        FederatedHarness(ReferenceLinearBackend(), config).run(prepared)


def test_harness_abort_check_stops_before_training():
    prepared = _prepared()
    harness = FederatedHarness(
        ReferenceLinearBackend(),
        FederatedConfig(num_clients=4, rounds=1),
        abort_check=lambda: True,
    )
    with pytest.raises(FederatedAborted):
        harness.run(prepared)
