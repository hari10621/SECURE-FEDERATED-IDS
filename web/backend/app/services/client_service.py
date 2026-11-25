"""Client configuration records for the local coordinator."""
from __future__ import annotations

import uuid
import threading
from ..domain.federated.independent_client import Worker, ProcessClient

from sqlalchemy import func, select

from ..db import Database
from ..enums import ClientStatus
from ..errors import ConflictError, NotFoundError
from ..models import Client


class ClientService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.workers = {}
        self.lock = threading.RLock()

    def pid(self, client_id):
        with self.lock:
            worker = self.workers.get(client_id)
            return worker.pid if worker and worker.process.poll() is None else None

    def close(self):
        with self.lock:
            for worker in self.workers.values():
                worker.close()
            self.workers.clear()

    def restore_enabled(self):
        with self.db.session() as session:
            ids = list(session.scalars(select(Client.id).where(Client.status == ClientStatus.ENABLED.value)))
        for client_id in ids:
            self.update(client_id, status=ClientStatus.ENABLED, config=None)

    def participant(self, **kwargs):
        client = ProcessClient(**kwargs)
        with self.lock:
            if not self.pid(client.client_id):
                raise ConflictError("Selected client is disconnected. Enable it before training.")
            client.exchange = self.workers[client.client_id].exchange
        return client

    def replay(self, client_id, features):
        with self.lock:
            worker = self.workers.get(client_id)
            if not self.pid(client_id):
                raise ConflictError("Enable this client before replaying an attack sample.")
        token = uuid.uuid4().hex
        try:
            reply = worker.exchange({"action": "replay", "client": {"client_id": client_id},
                                     "token": token, "features": features})
        except (OSError, ValueError, RuntimeError) as exc:
            raise ConflictError("Client disconnected during replay.") from exc
        if (reply.get("token") != token or reply.get("client_id") != client_id
                or reply.get("pid") != worker.pid or reply.get("features") != features):
            raise ConflictError("Received an invalid replay response from the worker.")
        return reply

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
        with self.lock, self.db.session() as session:
            client = session.get(Client, client_id)
            if client is None:
                raise NotFoundError(f"client not found: {client_id}")
            if status == ClientStatus.ENABLED and not self.pid(client_id):
                self.workers[client_id] = Worker(client_id)
            elif status is not None and status != ClientStatus.ENABLED:
                worker = self.workers.pop(client_id, None)
                if worker:
                    worker.close()
            if status is not None:
                client.status = status.value
            if config is not None:
                client.config = config
            session.flush()
            session.refresh(client)
            return client
