from __future__ import annotations

import pytest

from app.domain.model import (
    artifact_filename,
    build_gru_model,
    chunk_count,
    flatten_gru_weights,
    keras_available,
    model_description,
    parameter_count,
    parameter_specs,
    read_weight_artifact,
    unflatten_gru_weights,
    write_weight_artifact,
)
from app.errors import InputValidationError, UnavailableError


def test_parameter_count_matches_legacy_inference():
    assert parameter_count(48) == 422_337
    assert chunk_count(48) == 104
    assert chunk_count(48, slot_count=4096) == 104


def test_model_description_matches_legacy_factory():
    description = model_description(48)
    assert description["input_shape"] == [1, 48]
    assert [layer["type"] for layer in description["layers"] if layer["type"] == "GRU"] == [
        "GRU",
        "GRU",
        "GRU",
    ]
    assert [layer["units"] for layer in description["layers"] if layer["type"] == "GRU"] == [
        256,
        128,
        64,
    ]
    assert description["optimizer"]["learning_rate"] == 0.0001
    assert description["loss"] == "binary_crossentropy"


def test_weight_roundtrip_is_lossless():
    specs = parameter_specs(6)
    flat = [float(index) + 0.125 for index in range(sum(spec.size for spec in specs))]
    blocks = unflatten_gru_weights(flat, 6)
    assert len(blocks) == len(specs)
    assert flatten_gru_weights(blocks, 6) == flat


def test_flatten_accepts_nested_keras_weight_shapes():
    specs = parameter_specs(4)
    flat = [float(index) + 0.25 for index in range(sum(spec.size for spec in specs))]
    blocks = unflatten_gru_weights(flat, 4)
    nested = []
    for spec, block in zip(specs, blocks):
        if len(spec.shape) == 1:
            nested.append(block)
            continue
        rows, columns = spec.shape
        nested.append(
            [block[row * columns : (row + 1) * columns] for row in range(rows)]
        )
    assert flatten_gru_weights(nested, 4) == flat


def test_weight_count_mismatch_is_rejected():
    with pytest.raises(InputValidationError):
        unflatten_gru_weights([0.0] * 5, 48)
    with pytest.raises(InputValidationError):
        parameter_count(0)


def test_artifact_roundtrip_and_naming(tmp_path):
    specs = parameter_specs(4)
    flat = [index * 0.5 for index in range(sum(spec.size for spec in specs))]
    target = tmp_path / artifact_filename("insdn", 8)
    digest = write_weight_artifact(
        target,
        flat_weights=flat,
        specs=specs,
        model_name="gru",
        input_features=4,
        dataset_type="insdn",
        client_count=8,
    )
    assert len(digest) == 64
    loaded = read_weight_artifact(target)
    assert loaded["input_features"] == 4
    assert loaded["dataset_type"] == "insdn"
    assert loaded["client_count"] == 8
    assert [value for block in loaded["weights_blocks"] for value in block] == flat
    assert target.name == "insdn_8_model.json"


def test_artifact_filename_does_not_reuse_legacy_suffix():
    assert artifact_filename("insdn", 4) != artifact_filename("insdn", 8)
    assert artifact_filename("insdn", 12).endswith("_12_model.json")
    with pytest.raises(InputValidationError):
        artifact_filename("", 4)
    with pytest.raises(InputValidationError):
        artifact_filename("insdn", 0)


def test_gru_factory_fails_closed_without_tensorflow():
    if keras_available():
        pytest.skip("TensorFlow is installed in this environment")
    with pytest.raises(UnavailableError):
        build_gru_model(48)
