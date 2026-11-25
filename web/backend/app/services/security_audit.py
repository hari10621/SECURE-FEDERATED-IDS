"""Structured records written in the transaction that made the corresponding change."""

import time
from uuid import uuid4


def audit(
    db,
    category,
    *,
    client=None,
    organization=None,
    version=None,
    job=None,
    event=None,
    severity="info",
):
    db.execute(
        "INSERT INTO security_audit VALUES(?,?,?,?,?,?,?,?,?)",
        (
            uuid4().hex,
            time.time(),
            category,
            severity,
            client,
            organization,
            version,
            job,
            event,
        ),
    )
