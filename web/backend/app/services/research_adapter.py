"""Safe adapter for the read-only research repository.

The original scripts run at import time and write relative output directories.
They are never imported into the API process. Instead, a fixed allowlist maps a
validated dataset type and client count to an original script. A run workspace
is prepared under the application data directory; the original repository is
only read.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import Settings
from ..enums import DatasetType
from ..errors import InputValidationError, JobCancelled, ResearchExecutionDisabled, UnavailableError
from ..storage.paths import StoragePaths
from .security_service import SecurityService

ALLOWED_SCRIPTS: dict[DatasetType, dict[int, str | None]] = {
    DatasetType.INSDN: {
        2: "InSDN_2.py",
        3: "InSDN_3.py",
        4: "InSDN_4.py",
        8: "InSDN_8.py",
        12: "InSDN_12.py",
    },
    DatasetType.CICIDS2017: {
        2: "CICDDoS17_2.py",
        3: "CICDDoS17_3.py",
        4: "CICDDoS17_4.py",
        8: None,
        12: "CICDDoS17_12.py",
    },
    DatasetType.CICIDS2019: {
        2: "CICDDoS19_2.py",
        3: "CICDDoS19_3.py",
        4: "CICDDoD19_4.py",
        8: "CICDDoS19_8.py",
        12: "CICDDoS19_12.py",
    },
}

DATASET_FILENAMES: dict[DatasetType, str] = {
    DatasetType.INSDN: "Final_Binary_InSDN_Dataset.csv",
    DatasetType.CICIDS2017: "final_cicids2017_top48_features.csv",
    DatasetType.CICIDS2019: "final_cicids2019_top48_features.csv",
}


@dataclass(frozen=True)
class ResearchInvocation:
    command: list[str]
    cwd: Path
    env: dict[str, str]
    timeout_seconds: int
    run_dir: Path
    manifest_path: Path


class ResearchAdapter:
    def __init__(self, settings: Settings, paths: StoragePaths, security: SecurityService) -> None:
        self.settings = settings
        self.paths = paths
        self.security = security

    def script_for(self, dataset_type: DatasetType, client_count: int) -> str | None:
        return ALLOWED_SCRIPTS.get(dataset_type, {}).get(client_count)

    def target_reason(self, dataset_type: DatasetType, client_count: int) -> str | None:
        script = self.script_for(dataset_type, client_count)
        if script is None:
            return (
                f"no allowlisted research script exists for {dataset_type.value} "
                f"with {client_count} clients"
            )
        return None

    def availability(self, dataset_type: DatasetType, client_count: int) -> tuple[bool, str]:
        if not self.settings.enable_research_execution:
            return False, "Research execution is disabled by configuration."
        reason = self.target_reason(dataset_type, client_count)
        if reason:
            return False, reason
        script = self.script_for(dataset_type, client_count)
        assert script is not None
        if not self.settings.research_python:
            return False, "Research Python 3.8 executable is not configured."
        python = Path(self.settings.research_python)
        if not python.is_absolute() or not python.is_file():
            return False, "Configured research Python executable is not an absolute file path."
        repo = self.settings.research_repo_dir
        if not repo.is_dir():
            return False, "Research repository directory is missing."
        source = repo / script
        if not source.is_file():
            return False, f"Allowlisted research script is missing: {script}"
        return True, "Research execution is configured."

    def prepare_workspace(
        self,
        *,
        run_id: str,
        dataset_type: DatasetType,
        client_count: int,
        dataset_path: Path,
        dataset_sha256: str,
    ) -> ResearchInvocation:
        ok, reason = self.availability(dataset_type, client_count)
        if not ok:
            raise ResearchExecutionDisabled(reason)

        script_name = self.script_for(dataset_type, client_count)
        assert script_name is not None
        source_script = self.security.assert_within(
            self.settings.research_repo_dir / script_name,
            self.settings.research_repo_dir,
            label="research script",
        )
        if not source_script.is_file():
            raise UnavailableError(f"allowlisted research script is missing: {script_name}")

        dataset_source = self.security.assert_within(
            Path(dataset_path),
            self.paths.data_dir,
            label="dataset path",
        )
        if not dataset_source.is_file():
            raise InputValidationError("dataset file is missing")

        run_dir = self.paths.run_dir(run_id)
        repo_dir = run_dir / "repo"
        home_dir = run_dir / "home"
        tmp_dir = run_dir / "tmp"
        for directory in (run_dir, repo_dir, home_dir, tmp_dir):
            directory.mkdir(parents=True, exist_ok=True)

        copied_script = repo_dir / script_name
        shutil.copy2(source_script, copied_script)

        dataset_target = run_dir / DATASET_FILENAMES[dataset_type]
        shutil.copy2(dataset_source, dataset_target)

        manifest = {
            "run_id": run_id,
            "dataset_type": dataset_type.value,
            "client_count": client_count,
            "script": script_name,
            "dataset_sha256": dataset_sha256,
            "copied_script": copied_script.name,
            "dataset_filename": dataset_target.name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "note": "Original repository is read-only; this is a prepared run workspace.",
        }
        manifest_path = run_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

        python = str(Path(self.settings.research_python))
        env = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": str(home_dir),
            "TMPDIR": str(tmp_dir),
            "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": os.pathsep.join(
                [str(run_dir), str(self.paths.ckks_dir)]
            ),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        }
        return ResearchInvocation(
            command=[python, str(copied_script)],
            cwd=repo_dir,
            env=env,
            timeout_seconds=24 * 60 * 60,
            run_dir=run_dir,
            manifest_path=manifest_path,
        )

    def _terminate(self, process: subprocess.Popen[str]) -> None:
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass

    def execute(
        self,
        invocation: ResearchInvocation,
        *,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        if not self.settings.enable_research_execution:
            raise ResearchExecutionDisabled("research execution is disabled")
        if not invocation.command or Path(invocation.command[0]).resolve() != Path(
            self.settings.research_python or ""
        ).resolve():
            raise UnavailableError("research command failed validation")
        script = Path(invocation.command[1]).resolve()
        self.security.assert_within(script, invocation.run_dir, label="run script")
        if cancel_event is not None and cancel_event.is_set():
            raise JobCancelled("research job cancellation requested")

        kwargs: dict[str, Any] = {
            "cwd": invocation.cwd,
            "env": invocation.env,
            "shell": False,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "errors": "replace",
        }
        if os.name == "posix":
            kwargs["start_new_session"] = True
        process = subprocess.Popen(invocation.command, **kwargs)
        deadline = time.monotonic() + invocation.timeout_seconds
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._terminate(process)
                    process.communicate()
                    raise UnavailableError("research process timed out")
                try:
                    stdout, stderr = process.communicate(timeout=min(0.5, remaining))
                    break
                except subprocess.TimeoutExpired:
                    if cancel_event is not None and cancel_event.is_set():
                        self._terminate(process)
                        process.communicate()
                        raise JobCancelled("research job cancellation requested")
            if cancel_event is not None and cancel_event.is_set():
                raise JobCancelled("research job cancellation requested")
        finally:
            if process.poll() is None:
                self._terminate(process)
                process.communicate()

        result = {
            "returncode": process.returncode,
            "stdout_tail": (stdout or "")[-4000:],
            "stderr_tail": (stderr or "")[-4000:],
            "run_dir": str(invocation.run_dir),
            "manifest": str(invocation.manifest_path),
        }
        if process.returncode != 0:
            raise UnavailableError(
                "research process failed",
                details={"returncode": process.returncode},
            )
        return result
