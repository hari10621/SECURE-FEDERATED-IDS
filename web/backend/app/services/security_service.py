"""Local security helpers: path confinement, filename hygiene, optional token auth."""

from __future__ import annotations

import hmac
import re
from pathlib import Path

from ..config import Settings
from ..errors import ForbiddenError, InputValidationError, UnauthorizedError


class SecurityService:
    def __init__(self, settings: Settings) -> None:
        self._token = settings.api_token

    def require_token(self, authorization: str | None) -> None:
        if not self._token:
            return
        if not authorization or not authorization.startswith("Bearer "):
            raise UnauthorizedError("missing bearer token")
        supplied = authorization.removeprefix("Bearer ").strip()
        if not supplied or not hmac.compare_digest(supplied, self._token):
            raise UnauthorizedError("invalid bearer token")

    @staticmethod
    def sanitize_filename(filename: str | None) -> str:
        raw = (filename or "dataset.csv").replace("\\", "/")
        name = Path(raw).name
        name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
        name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name)
        name = re.sub(r"\s+", " ", name).strip(" .")
        if not name:
            name = "dataset.csv"
        return name[:160]

    @staticmethod
    def sanitize_display_name(name: str, *, fallback: str = "dataset") -> str:
        cleaned = re.sub(r"[\x00-\x1f\x7f]", "", (name or "").strip())
        cleaned = re.sub(r"\s+", " ", cleaned)
        if not cleaned:
            cleaned = fallback
        return cleaned[:120]

    @staticmethod
    def sanitize_column_name(name: str | None) -> str | None:
        if name is None:
            return None
        cleaned = re.sub(r"[\x00-\x1f\x7f]", "", name.strip())
        if not cleaned:
            raise InputValidationError("label_column must not be empty")
        if len(cleaned) > 160:
            raise InputValidationError("label_column is too long")
        return cleaned

    @staticmethod
    def assert_within(path: Path, root: Path, *, label: str = "path") -> Path:
        resolved = path.resolve()
        if not resolved.is_relative_to(root.resolve()):
            raise ForbiddenError(f"{label} is outside the approved directory")
        return resolved
