"""Durable, bounded FIFO of samples waiting to be uploaded.

Backed by SQLite (standard library) instead of an in-memory deque so that
samples survive an agent crash or restart while the server is unreachable.
WAL mode keeps writes cheap; when full, the *oldest* samples are dropped,
because recent data is more valuable for a monitoring system.
"""

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    payload TEXT NOT NULL
)
"""


class SampleBuffer:
    def __init__(self, path: Path | str, max_size: int) -> None:
        self.max_size = max_size
        self.dropped_total = 0
        self._lock = threading.Lock()
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.execute(_SCHEMA)

    def put(self, sample: dict[str, Any]) -> None:
        with self._lock:
            self._db.execute("INSERT INTO samples (payload) VALUES (?)", (json.dumps(sample),))
            overflow = self._size() - self.max_size
            if overflow > 0:
                self._db.execute(
                    "DELETE FROM samples WHERE id IN (SELECT id FROM samples ORDER BY id LIMIT ?)",
                    (overflow,),
                )
                self.dropped_total += overflow

    def peek(self, limit: int) -> list[tuple[int, dict[str, Any]]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, payload FROM samples ORDER BY id LIMIT ?", (limit,)
            ).fetchall()
        return [(row_id, json.loads(payload)) for row_id, payload in rows]

    def ack(self, ids: list[int]) -> None:
        if not ids:
            return
        with self._lock:
            self._db.executemany("DELETE FROM samples WHERE id = ?", [(i,) for i in ids])

    def size(self) -> int:
        with self._lock:
            return self._size()

    def _size(self) -> int:
        return int(self._db.execute("SELECT COUNT(*) FROM samples").fetchone()[0])

    def close(self) -> None:
        with self._lock:
            self._db.close()
