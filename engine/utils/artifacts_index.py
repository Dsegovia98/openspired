"""
utils/artifacts_index.py — Persistent metadata index for generated tickets.

Stores per-ticket metadata not represented in _Registro.md, such as tags,
usage/tokens/cost, revisions and run linkage.
"""
from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import WORKSPACE_DIR

INDEX_PATH = WORKSPACE_DIR / "logs" / ".artifacts_index.json"


@contextmanager
def _file_lock(path: Path):
    lock_path = path.with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    if sys.platform != "win32":
        import fcntl
        with open(lock_path, "w") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)
    else:
        import time
        waited = 0.0
        while lock_path.exists() and waited < 10.0:
            time.sleep(0.1)
            waited += 0.1
        lock_path.touch()
        try:
            yield
        finally:
            lock_path.unlink(missing_ok=True)


def _read_index() -> dict[str, Any]:
    if not INDEX_PATH.exists():
        return {"tickets": {}, "updated_at": ""}
    try:
        data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"tickets": {}, "updated_at": ""}
        tickets = data.get("tickets", {})
        if not isinstance(tickets, dict):
            tickets = {}
        return {"tickets": tickets, "updated_at": str(data.get("updated_at", ""))}
    except Exception:
        return {"tickets": {}, "updated_at": ""}


def load_artifacts_index() -> dict[str, dict[str, Any]]:
    data = _read_index()
    return data.get("tickets", {})


def upsert_ticket_metadata(ticket_id: str, metadata: dict[str, Any]) -> None:
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _file_lock(INDEX_PATH):
        data = _read_index()
        tickets = data.get("tickets", {})
        existing = tickets.get(ticket_id, {})
        if not isinstance(existing, dict):
            existing = {}

        merged = {**existing, **metadata}
        merged["ticket_id"] = ticket_id
        merged["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        tickets[ticket_id] = merged

        payload = {
            "tickets": tickets,
            "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        INDEX_PATH.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
