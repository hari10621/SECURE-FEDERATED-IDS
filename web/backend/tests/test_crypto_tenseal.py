from __future__ import annotations

import pytest

pytest.importorskip("tenseal")

from app.domain.crypto import (
    CKKS_BATCH_SIZE,
    CryptoUnavailable,
    TensealCKKSBackend,
    TrustedAuthority,
    chunk_count,
    default_ckks_params,
)
from app.domain.dataset import preprocess
from app.domain.federated import (
    EncryptedClientUpdate,
    EncryptedFederatedHarness,
    FLServer,
    FederatedConfig,
    ReferenceLinearBackend,
    ciphertext_digest,
    delta_weights,
)


@pytest.fixture()
def keyed():
    authority = TrustedAuthority(default_ckks_params(parties=4, threshold=2))
    material = authority.generate()
    authority.decommission()
    server = TensealCKKSBackend.from_material(material, include_secret=False)
    keyring = TensealCKKSBackend.from_material(material, include_secret=True)
    return material, server, keyring


def _update(
    server: FLServer,
    crypto: TensealCKKSBackend,
    client_id: str,
    values: list[float],
    *,
    sample_count: int = 10,
    digest: str | None = None,
) -> EncryptedClientUpdate:
    auth = server.issue_auth_token(client_id)
    chunks = crypto.encrypt_vector(values)
    return EncryptedClientUpdate(
        client_id=client_id,
        chunks=tuple(chunks),
        sample_count=sample_count,
        ciphertext_digest=digest or ciphertext_digest(chunks),
        round_index=0,
        auth_token=auth.token,
        timestamp=auth.timestamp,
        nonce=auth.nonce,
    )


def _prepared():
    rows = [
        [((index * (position + 3)) % 17) / 10.0 for position in range(4)]
        for index in range(80)
    ]
    labels = [index % 2 for index in range(80)]
    return preprocess(
        rows,
        labels,
        feature_names=[f"f{index}" for index in range(4)],
        mode="clean",
        seed=42,
    )


def test_ckks_round_trip_and_public_context_cannot_decrypt(keyed):
    _material, server, keyring = keyed
    assert server.status().available is True
    assert server.has_secret_key is False
    assert keyring.has_secret_key is True

    chunks = server.encrypt_vector([0.5, -1.25, 3.0])
    assert all(server.validate_ciphertext(chunk) for chunk in chunks)
    decrypted = keyring.decrypt_aggregate(chunks, 3)
    assert decrypted == pytest.approx([0.5, -1.25, 3.0], abs=1e-6)

    with pytest.raises(CryptoUnavailable):
        server.decrypt_aggregate(chunks, 3)


def test_chunk_count_matches_paper_gru():
    assert chunk_count(422_337, CKKS_BATCH_SIZE) == 104


def test_delta_rule_matches_paper():
    assert delta_weights([2.0, 4.0], [1.0, 1.0]) == [1.0, 3.0]


def test_homomorphic_aggregation_and_digest(keyed):
    _material, server, keyring = keyed
    fl = FLServer(
        num_clients=4,
        threshold=2,
        expected_parameter_count=3,
        weighting="sample",
    )
    fl.register_client("c1", 10)
    fl.register_client("c2", 30)

    result = fl.aggregate_encrypted(
        [
            _update(fl, server, "c1", [1.0, 2.0, 3.0], sample_count=10),
            _update(fl, server, "c2", [3.0, 4.0, 5.0], sample_count=30),
        ],
        server,
    )

    assert result.aborted is False
    assert result.aggregate_digest == ciphertext_digest(result.chunks)
    decrypted = keyring.decrypt_aggregate(list(result.chunks), 3)
    assert decrypted == pytest.approx([2.5, 3.5, 4.5], abs=1e-5)


def test_tampered_ciphertext_is_flagged(keyed):
    _material, server, _keyring = keyed
    fl = FLServer(
        num_clients=4,
        threshold=1,
        expected_parameter_count=3,
        byzantine_max_faults=0,
    )
    fl.register_client("c1", 10)

    result = fl.aggregate_encrypted(
        [_update(fl, server, "c1", [1.0, 2.0, 3.0], digest="0" * 64)],
        server,
    )

    assert result.aborted is True
    assert "c1" in result.byzantine_flagged


def test_replayed_auth_token_is_rejected(keyed):
    _material, server, _keyring = keyed
    fl = FLServer(
        num_clients=4,
        threshold=1,
        expected_parameter_count=3,
    )
    fl.register_client("c1", 10)
    update = _update(fl, server, "c1", [1.0, 2.0, 3.0])

    first = fl.aggregate_encrypted([update], server)
    assert first.aborted is False

    second = fl.aggregate_encrypted([update], server)
    assert second.aborted is True
    assert "c1" in second.byzantine_flagged


def test_byzantine_abort_exceeding_tmax(keyed):
    _material, server, _keyring = keyed
    fl = FLServer(
        num_clients=4,
        threshold=1,
        expected_parameter_count=3,
        byzantine_max_faults=2,
    )
    for index in range(1, 5):
        fl.register_client(f"c{index}", 10)

    updates = [
        _update(fl, server, f"c{index}", [1.0, 2.0, 3.0], digest="bad")
        for index in range(1, 4)
    ]
    updates.append(_update(fl, server, "c4", [1.0, 2.0, 3.0]))

    result = fl.aggregate_encrypted(updates, server)

    assert result.aborted is True
    assert "Byzantine threshold exceeded" in str(result.reason)
    assert len(result.byzantine_flagged) == 3


def test_encrypted_harness_end_to_end(keyed):
    material, server, keyring = keyed
    config = FederatedConfig(
        num_clients=4,
        rounds=1,
        local_epochs=1,
        batch_size=8,
        learning_rate=0.05,
        threshold=2,
        weighting="sample",
        seed=42,
    )

    result = EncryptedFederatedHarness(
        ReferenceLinearBackend(),
        config,
        server,
        keyring,
        context_hash=material.context_hash,
    ).run(_prepared())

    assert result["encrypted"] is True
    assert result["encryption_claimed"] is True
    assert result["ciphertext"]["chunks_per_update"] == 1
    assert result["ta_context_hash"] == material.context_hash
    assert result["rounds"][0]["aborted"] is False
    assert result["final_metrics"] is not None
    assert "weights" not in result["rounds"][0]["updates"][0]
