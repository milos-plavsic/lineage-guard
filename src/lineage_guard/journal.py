from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

from lineage_guard.events import QualityEvent

MAX_JOURNAL_RESULT_BYTES = 2_000_000
MAX_TRANSITION_DETAIL_BYTES = 65_536
_STAGE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class JournalError(RuntimeError):
    """Raised when an event cannot safely transition journal state."""


class ClaimDisposition(StrEnum):
    NEW = "new"
    RETRY = "retry"
    DUPLICATE = "duplicate"
    BUSY = "busy"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class EventClaim:
    disposition: ClaimDisposition
    event_id: str
    attempts: int
    result: dict[str, Any] | None = None


class EventJournal:
    """Durable event deduplication and crash-recovery journal backed by SQLite."""

    def __init__(self, path: Path, *, lease_seconds: int = 300) -> None:
        if not 1 <= lease_seconds <= 3_600:
            raise ValueError("journal lease must be between 1 and 3600 seconds")
        self._path = path
        self._lease = timedelta(seconds=lease_seconds)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS quality_events (
                    event_id TEXT PRIMARY KEY,
                    payload_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('processing', 'completed', 'failed')),
                    attempts INTEGER NOT NULL CHECK(attempts > 0),
                    incident_id TEXT,
                    result_json TEXT,
                    error_code TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS event_transitions (
                    transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    detail_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(event_id) REFERENCES quality_events(event_id)
                )
                """
            )

    def claim(self, event: QualityEvent) -> EventClaim:
        now = datetime.now(UTC)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload_sha256, status, attempts, result_json, updated_at "
                "FROM quality_events WHERE event_id = ?",
                (event.event_id,),
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO quality_events "
                    "(event_id, payload_sha256, status, attempts, updated_at) "
                    "VALUES (?, ?, 'processing', 1, ?)",
                    (event.event_id, event.payload_sha256, now.isoformat()),
                )
                self._insert_transition(connection, event.event_id, "claimed", {}, now)
                return EventClaim(ClaimDisposition.NEW, event.event_id, 1)
            digest, status, attempts, result_json, updated_at = row
            if digest != event.payload_sha256:
                return EventClaim(ClaimDisposition.CONFLICT, event.event_id, attempts)
            if status == "completed":
                result = json.loads(result_json) if result_json else None
                return EventClaim(ClaimDisposition.DUPLICATE, event.event_id, attempts, result)
            lease_expired = now - datetime.fromisoformat(updated_at) >= self._lease
            if status == "processing" and not lease_expired:
                return EventClaim(ClaimDisposition.BUSY, event.event_id, attempts)
            attempts += 1
            connection.execute(
                "UPDATE quality_events SET status = 'processing', attempts = ?, "
                "error_code = NULL, updated_at = ? WHERE event_id = ?",
                (attempts, now.isoformat(), event.event_id),
            )
            self._insert_transition(connection, event.event_id, "retry_claimed", {}, now)
            return EventClaim(ClaimDisposition.RETRY, event.event_id, attempts)

    def record_transition(
        self, event_id: str, stage: str, detail: dict[str, Any] | None = None
    ) -> None:
        if not _STAGE.fullmatch(stage):
            raise ValueError("journal stage must be lowercase snake_case up to 64 characters")
        with self._connect() as connection:
            try:
                self._insert_transition(
                    connection, event_id, stage, detail or {}, datetime.now(UTC)
                )
            except sqlite3.IntegrityError as error:
                raise JournalError("cannot record a transition for an unknown event") from error

    def history(self, event_id: str) -> tuple[dict[str, Any], ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT stage, detail_json, created_at FROM event_transitions "
                "WHERE event_id = ? ORDER BY transition_id",
                (event_id,),
            ).fetchall()
        return tuple(
            {"stage": stage, "detail": json.loads(detail), "created_at": created_at}
            for stage, detail, created_at in rows
        )

    def complete(self, event_id: str, incident_id: str, result: dict[str, Any]) -> None:
        rendered = json.dumps(result, sort_keys=True, separators=(",", ":"))
        if len(rendered.encode()) > MAX_JOURNAL_RESULT_BYTES:
            raise JournalError("journal result exceeds the safety limit")
        self._transition(
            event_id,
            "completed",
            incident_id=incident_id,
            result_json=rendered,
            error_code=None,
        )

    def fail(self, event_id: str, error_code: str) -> None:
        if not error_code or len(error_code) > 128:
            raise ValueError("journal error code must contain 1 to 128 characters")
        self._transition(
            event_id,
            "failed",
            incident_id=None,
            result_json=None,
            error_code=error_code,
        )

    def _transition(
        self,
        event_id: str,
        status: str,
        *,
        incident_id: str | None,
        result_json: str | None,
        error_code: str | None,
    ) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE quality_events SET status = ?, incident_id = ?, result_json = ?, "
                "error_code = ?, updated_at = ? "
                "WHERE event_id = ? AND status = 'processing'",
                (
                    status,
                    incident_id,
                    result_json,
                    error_code,
                    datetime.now(UTC).isoformat(),
                    event_id,
                ),
            )
            if cursor.rowcount != 1:
                raise JournalError("event is not in a processing state")
            self._insert_transition(
                connection,
                event_id,
                status,
                {"incident_id": incident_id, "error_code": error_code},
                datetime.now(UTC),
            )

    @staticmethod
    def _insert_transition(
        connection: sqlite3.Connection,
        event_id: str,
        stage: str,
        detail: dict[str, Any],
        created_at: datetime,
    ) -> None:
        rendered = json.dumps(detail, sort_keys=True, separators=(",", ":"))
        if len(rendered.encode()) > MAX_TRANSITION_DETAIL_BYTES:
            raise JournalError("journal transition detail exceeds the safety limit")
        connection.execute(
            "INSERT INTO event_transitions (event_id, stage, detail_json, created_at) "
            "VALUES (?, ?, ?, ?)",
            (event_id, stage, rendered, created_at.isoformat()),
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=5)
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection
