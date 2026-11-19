from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

from app.config import Settings
from app.enums import DatasetType
from app.errors import ForbiddenError, JobCancelled, ResearchExecutionDisabled
from app.services.research_adapter import (
    ALLOWED_SCRIPTS,
    DATASET_FILENAMES,
    ResearchAdapter,
)
from app.services.security_service import SecurityService
from app.storage.paths import StoragePaths


@pytest.fixture
def research_env(tmp_path):
    repo = tmp_path / "research"
    repo.mkdir()
    script = repo / "InSDN_4.py"
    script.write_text("print('fake research script')\n", encoding="utf-8")
    settings = Settings(
        base_dir=tmp_path,
        data_dir=tmp_path / "var",
        database_url=f"sqlite:///{tmp_path / 'research.db'}",
        research_repo_dir=repo,
        research_python=sys.executable,
        enable_research_execution=True,
    )
    paths = StoragePaths(settings)
    paths.ensure()
    adapter = ResearchAdapter(settings, paths, SecurityService(settings))
    dataset = paths.datasets_dir / "source.csv"
    dataset.write_text("f0,Label\n0.1,0\n", encoding="utf-8")
    return settings, paths, adapter, repo, script, dataset


def test_allowlist_matches_known_variants():
    assert ALLOWED_SCRIPTS[DatasetType.INSDN][4] == "InSDN_4.py"
    assert ALLOWED_SCRIPTS[DatasetType.INSDN][8] == "InSDN_8.py"
    assert ALLOWED_SCRIPTS[DatasetType.INSDN][12] == "InSDN_12.py"
    assert ALLOWED_SCRIPTS[DatasetType.CICIDS2017][8] is None
    assert ALLOWED_SCRIPTS[DatasetType.CICIDS2019][4] == "CICDDoD19_4.py"


def test_prepare_workspace_is_isolated_and_read_only(research_env):
    settings, paths, adapter, repo, script, dataset = research_env
    original_script = script.read_bytes()
    original_dataset = dataset.read_bytes()

    invocation = adapter.prepare_workspace(
        run_id="run-1",
        dataset_type=DatasetType.INSDN,
        client_count=4,
        dataset_path=dataset,
        dataset_sha256="a" * 64,
    )

    assert invocation.command[0] == sys.executable
    assert Path(invocation.command[1]).is_file()
    assert invocation.cwd == invocation.run_dir / "repo"
    assert invocation.run_dir.is_relative_to(paths.runs_dir)
    assert invocation.manifest_path.is_file()
    assert invocation.env["HOME"] == str(invocation.run_dir / "home")
    assert "SECUREFED_API_TOKEN" not in invocation.env

    assert (invocation.run_dir / DATASET_FILENAMES[DatasetType.INSDN]).read_bytes() == original_dataset
    assert script.read_bytes() == original_script
    assert set(p.name for p in (invocation.run_dir / "repo").iterdir()) == {"InSDN_4.py"}


def test_missing_variant_has_explicit_reason(research_env):
    _settings, _paths, adapter, _repo, _script, _dataset = research_env
    reason = adapter.target_reason(DatasetType.CICIDS2017, 8)
    assert reason is not None
    assert "no allowlisted research script" in reason


def test_disabled_execution_fails_closed(tmp_path):
    settings = Settings(
        base_dir=tmp_path,
        data_dir=tmp_path / "var",
        database_url=f"sqlite:///{tmp_path / 'disabled.db'}",
        research_repo_dir=tmp_path / "missing",
        enable_research_execution=False,
    )
    paths = StoragePaths(settings)
    paths.ensure()
    adapter = ResearchAdapter(settings, paths, SecurityService(settings))
    assert adapter.availability(DatasetType.INSDN, 4)[0] is False
    with pytest.raises(ResearchExecutionDisabled):
        adapter.prepare_workspace(
            run_id="run-2",
            dataset_type=DatasetType.INSDN,
            client_count=4,
            dataset_path=paths.datasets_dir / "x.csv",
            dataset_sha256="b" * 64,
        )


def test_dataset_outside_data_dir_is_rejected(research_env, tmp_path):
    _settings, _paths, adapter, _repo, _script, _dataset = research_env
    outside = tmp_path / "outside.csv"
    outside.write_text("f0,Label\n0.1,0\n", encoding="utf-8")
    with pytest.raises(ForbiddenError):
        adapter.prepare_workspace(
            run_id="run-3",
            dataset_type=DatasetType.INSDN,
            client_count=4,
            dataset_path=outside,
            dataset_sha256="c" * 64,
        )


def test_execute_terminates_worker_on_cancellation(research_env):
    _settings, _paths, adapter, _repo, script, dataset = research_env
    script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    invocation = adapter.prepare_workspace(
        run_id="run-cancel",
        dataset_type=DatasetType.INSDN,
        client_count=4,
        dataset_path=dataset,
        dataset_sha256="d" * 64,
    )
    cancel_event = threading.Event()
    outcome: dict[str, BaseException] = {}

    def run_worker() -> None:
        try:
            adapter.execute(invocation, cancel_event=cancel_event)
        except BaseException as exc:  # noqa: BLE001 - asserted below
            outcome["error"] = exc

    worker = threading.Thread(target=run_worker)
    started = time.monotonic()
    worker.start()
    time.sleep(0.4)
    cancel_event.set()
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert isinstance(outcome.get("error"), JobCancelled)
    assert time.monotonic() - started < 5
