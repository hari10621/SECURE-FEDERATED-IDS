"""Client configuration records.

Phase 3 has no independent client runtime. These endpoints persist configuration
only and report ``runtime_connected: false``; they do not pretend clients exist.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from ..db import Database
from ..enums import ClientStatus
from ..errors import ConflictError, NotFoundError
from ..models import Client


class ClientService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, *, name: str, config: dict) -> Client:
        with self.db.session() as session:
            existing = session.scalar(select(Client).where(Client.name == name))
            if existing is not None:
                raise ConflictError(f"client already exists: {name}")
            client = Client(
                id=uuid.uuid4().hex,
                name=name,
                status=ClientStatus.CONFIGURED.value,
                config=config,
            )
            session.add(client)
            session.flush()
            session.refresh(client)
            return client

    def list(self, *, limit: int = 50, offset: int = 0) -> tuple[list[Client], int]:
        with self.db.session() as session:
            total = session.scalar(select(func.count()).select_from(Client)) or 0
            rows = list(
                session.scalars(
                    select(Client).order_by(Client.created_at.asc()).limit(limit).offset(offset)
                )
            )
        return rows, total

    def get(self, client_id: str) -> Client:
        with self.db.session() as session:
            client = session.get(Client, client_id)
            if client is None:
                raise NotFoundError(f"client not found: {client_id}")
            return client

    def update(
        self,
        client_id: str,
        *,
        status: ClientStatus | None,
        config: dict | None,
    ) -> Client:
        with self.db.session() as session:
            client = session.get(Client, client_id)
            if client is None:
                raise NotFoundError(f"client not found: {client_id}")
            if status is not None:
                client.status = status.value
            if config is not None:
                client.config = config
            session.flush()
            session.refresh(client)
            return client
