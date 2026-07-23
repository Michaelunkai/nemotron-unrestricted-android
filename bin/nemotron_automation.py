"""Shared durable automation primitives for the Nemotron runtime.

This module has no network side effects. Callers supply the operation to retry
and decide whether it is safe to retry.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import os
import pathlib
import random
import re
import sqlite3
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable, Iterator
from typing import Any, TypeVar


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_STATE = ROOT / "runtime" / ".codex" / "automation"
SAFE_MODE_FILE = DEFAULT_STATE / "resilience" / "safe-mode.json"
SECRET_PATTERN = re.compile(
    r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?|api[_-]?key\s*[:=]\s*|token\s*[:=]\s*|password\s*[:=]\s*)([^\s,;]+)"
)
T = TypeVar("T")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def redact(value: Any) -> Any:
    if isinstance(value, str):
        return SECRET_PATTERN.sub(lambda match: match.group(1) + "<redacted>", value)
    if isinstance(value, dict):
        return {
            key: ("<redacted>" if re.search(r"(?i)(secret|token|password|api.?key|authorization)", str(key)) else redact(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def atomic_write(path: pathlib.Path, payload: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = pathlib.Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as destination:
            destination.write(payload)
            destination.flush()
            os.fsync(destination.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def safe_mode_status(path: pathlib.Path | None = None) -> dict[str, Any]:
    """Read the fail-safe network mode without initializing other runtime state."""
    state_path = path or SAFE_MODE_FILE
    try:
        value = json.loads(state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {"active": False, "mode": "normal", "reason": None}
    active = value.get("active") is True
    return {
        "active": active,
        "mode": "local-only" if active else "normal",
        "reason": str(value.get("reason") or "")[:240] if active else None,
        "enabledEpoch": value.get("enabledEpoch") if active else None,
    }


class AutomationState:
    def __init__(self, root: pathlib.Path = DEFAULT_STATE) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.database = self.root / "state.db"
        self.log_path = self.root / "events.jsonl"
        self.metrics_path = self.root / "metrics.prom"
        self._migrate()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _migrate(self) -> None:
        try:
            with contextlib.closing(self.connect()) as connection, connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS schema_meta (
                      version INTEGER NOT NULL
                    );
                    INSERT INTO schema_meta(version)
                      SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM schema_meta);
                    CREATE TABLE IF NOT EXISTS cache (
                      namespace TEXT NOT NULL,
                      key TEXT NOT NULL,
                      value_json TEXT NOT NULL,
                      created_at INTEGER NOT NULL,
                      expires_at INTEGER,
                      PRIMARY KEY(namespace, key)
                    );
                    CREATE INDEX IF NOT EXISTS cache_expires ON cache(expires_at);
                    CREATE TABLE IF NOT EXISTS circuits (
                      name TEXT PRIMARY KEY,
                      failures INTEGER NOT NULL DEFAULT 0,
                      state TEXT NOT NULL DEFAULT 'closed',
                      opened_at INTEGER,
                      cool_down_seconds INTEGER NOT NULL DEFAULT 30,
                      threshold INTEGER NOT NULL DEFAULT 5,
                      last_error TEXT,
                      updated_at INTEGER NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS counters (
                      name TEXT PRIMARY KEY,
                      value REAL NOT NULL DEFAULT 0,
                      updated_at INTEGER NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS gauges (
                      name TEXT PRIMARY KEY,
                      value REAL NOT NULL DEFAULT 0,
                      updated_at INTEGER NOT NULL
                    );
                    """
                )
        except sqlite3.DatabaseError:
            quarantine = self.database.with_name(
                f"state.corrupt-{int(time.time())}-{hashlib.sha256(self.database.read_bytes()).hexdigest()[:12]}.db"
            )
            os.replace(self.database, quarantine)
            for suffix in ("-wal", "-shm"):
                sidecar = pathlib.Path(str(self.database) + suffix)
                if sidecar.exists():
                    os.replace(sidecar, pathlib.Path(str(quarantine) + suffix))
            with contextlib.closing(self.connect()) as connection, connection:
                connection.executescript(
                    """
                    CREATE TABLE schema_meta(version INTEGER NOT NULL);
                    INSERT INTO schema_meta VALUES(1);
                    CREATE TABLE cache(namespace TEXT NOT NULL,key TEXT NOT NULL,value_json TEXT NOT NULL,created_at INTEGER NOT NULL,expires_at INTEGER,PRIMARY KEY(namespace,key));
                    CREATE INDEX cache_expires ON cache(expires_at);
                    CREATE TABLE circuits(name TEXT PRIMARY KEY,failures INTEGER NOT NULL DEFAULT 0,state TEXT NOT NULL DEFAULT 'closed',opened_at INTEGER,cool_down_seconds INTEGER NOT NULL DEFAULT 30,threshold INTEGER NOT NULL DEFAULT 5,last_error TEXT,updated_at INTEGER NOT NULL);
                    CREATE TABLE counters(name TEXT PRIMARY KEY,value REAL NOT NULL DEFAULT 0,updated_at INTEGER NOT NULL);
                    CREATE TABLE gauges(name TEXT PRIMARY KEY,value REAL NOT NULL DEFAULT 0,updated_at INTEGER NOT NULL);
                    """
                )

    @staticmethod
    def _name(value: str, field: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", value):
            raise ValueError(f"{field}_invalid")
        return value

    def cache_set(self, namespace: str, key: str, value: Any, ttl_seconds: int | None) -> None:
        namespace = self._name(namespace, "namespace")
        key = self._name(key, "key")
        if ttl_seconds is not None and not 1 <= ttl_seconds <= 31_536_000:
            raise ValueError("ttl_invalid")
        now = int(time.time())
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        if len(encoded.encode()) > 1_048_576:
            raise ValueError("value_too_large")
        with contextlib.closing(self.connect()) as connection, connection:
            connection.execute(
                "INSERT INTO cache(namespace,key,value_json,created_at,expires_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(namespace,key) DO UPDATE SET value_json=excluded.value_json,created_at=excluded.created_at,expires_at=excluded.expires_at",
                (namespace, key, encoded, now, now + ttl_seconds if ttl_seconds else None),
            )

    def cache_get(self, namespace: str, key: str) -> dict[str, Any] | None:
        namespace = self._name(namespace, "namespace")
        key = self._name(key, "key")
        now = int(time.time())
        with contextlib.closing(self.connect()) as connection, connection:
            row = connection.execute(
                "SELECT value_json,created_at,expires_at FROM cache WHERE namespace=? AND key=?",
                (namespace, key),
            ).fetchone()
            if not row:
                return None
            if row["expires_at"] is not None and row["expires_at"] <= now:
                connection.execute("DELETE FROM cache WHERE namespace=? AND key=?", (namespace, key))
                return None
            return {
                "value": json.loads(row["value_json"]),
                "createdAtEpoch": row["created_at"],
                "expiresAtEpoch": row["expires_at"],
                "ageSeconds": max(0, now - row["created_at"]),
            }

    def cache_delete(self, namespace: str, key: str) -> bool:
        with contextlib.closing(self.connect()) as connection, connection:
            cursor = connection.execute(
                "DELETE FROM cache WHERE namespace=? AND key=?",
                (self._name(namespace, "namespace"), self._name(key, "key")),
            )
            return cursor.rowcount > 0

    def prune(self) -> int:
        with contextlib.closing(self.connect()) as connection, connection:
            cursor = connection.execute(
                "DELETE FROM cache WHERE expires_at IS NOT NULL AND expires_at<=?",
                (int(time.time()),),
            )
            return cursor.rowcount

    def vacuum(self) -> None:
        with contextlib.closing(self.connect()) as connection, connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        connection = sqlite3.connect(self.database, timeout=10, isolation_level=None)
        try:
            connection.execute("VACUUM")
        finally:
            connection.close()

    def circuit_status(self, name: str) -> dict[str, Any]:
        name = self._name(name, "circuit")
        now = int(time.time())
        with contextlib.closing(self.connect()) as connection, connection:
            row = connection.execute("SELECT * FROM circuits WHERE name=?", (name,)).fetchone()
            if not row:
                return {"name": name, "state": "closed", "failures": 0, "allow": True}
            state = row["state"]
            if state == "open" and now - (row["opened_at"] or now) >= row["cool_down_seconds"]:
                state = "half-open"
                connection.execute(
                    "UPDATE circuits SET state='half-open',updated_at=? WHERE name=?", (now, name)
                )
            return {
                "name": name,
                "state": state,
                "failures": row["failures"],
                "allow": state in {"closed", "half-open"},
                "threshold": row["threshold"],
                "coolDownSeconds": row["cool_down_seconds"],
                "lastError": row["last_error"],
            }

    def circuit_success(self, name: str) -> None:
        name = self._name(name, "circuit")
        with contextlib.closing(self.connect()) as connection, connection:
            connection.execute(
                "INSERT INTO circuits(name,failures,state,opened_at,last_error,updated_at) VALUES(?,0,'closed',NULL,NULL,?) "
                "ON CONFLICT(name) DO UPDATE SET failures=0,state='closed',opened_at=NULL,last_error=NULL,updated_at=excluded.updated_at",
                (name, int(time.time())),
            )

    def circuit_failure(self, name: str, error: str, threshold: int = 5, cool_down_seconds: int = 30) -> dict[str, Any]:
        name = self._name(name, "circuit")
        if not 1 <= threshold <= 20 or not 1 <= cool_down_seconds <= 3600:
            raise ValueError("circuit_limits_invalid")
        now = int(time.time())
        with contextlib.closing(self.connect()) as connection, connection:
            row = connection.execute("SELECT failures FROM circuits WHERE name=?", (name,)).fetchone()
            failures = (row["failures"] if row else 0) + 1
            state = "open" if failures >= threshold else "closed"
            connection.execute(
                "INSERT INTO circuits(name,failures,state,opened_at,cool_down_seconds,threshold,last_error,updated_at) VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET failures=excluded.failures,state=excluded.state,opened_at=excluded.opened_at,cool_down_seconds=excluded.cool_down_seconds,threshold=excluded.threshold,last_error=excluded.last_error,updated_at=excluded.updated_at",
                (name, failures, state, now if state == "open" else None, cool_down_seconds, threshold, str(redact(error))[:500], now),
            )
        return self.circuit_status(name)

    def log(self, level: str, module: str, message: str, **fields: Any) -> None:
        if level not in {"debug", "info", "warning", "error"}:
            raise ValueError("level_invalid")
        module = self._name(module, "module")
        self.rotate_log()
        event = redact({
            "timestamp": utc_now(),
            "level": level,
            "module": module,
            "message": message[:1000],
            "fields": fields,
        })
        with self.log_path.open("a", encoding="utf-8") as destination:
            destination.write(json.dumps(event, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n")
            destination.flush()
            os.fsync(destination.fileno())
        os.chmod(self.log_path, 0o600)

    def rotate_log(self, maximum_bytes: int = 1_048_576, keep: int = 5) -> None:
        if not self.log_path.exists() or self.log_path.stat().st_size <= maximum_bytes:
            return
        oldest = self.log_path.with_suffix(f".jsonl.{keep}")
        if oldest.exists():
            oldest.unlink()
        for index in range(keep - 1, 0, -1):
            source = self.log_path.with_suffix(f".jsonl.{index}")
            if source.exists():
                os.replace(source, self.log_path.with_suffix(f".jsonl.{index + 1}"))
        os.replace(self.log_path, self.log_path.with_suffix(".jsonl.1"))

    def increment(self, name: str, amount: float = 1.0) -> None:
        name = self._name(name, "metric")
        with contextlib.closing(self.connect()) as connection, connection:
            connection.execute(
                "INSERT INTO counters(name,value,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET value=value+excluded.value,updated_at=excluded.updated_at",
                (name, amount, int(time.time())),
            )
        self.write_metrics()

    def set_gauge(self, name: str, value: float) -> None:
        name = self._name(name, "metric")
        if not isinstance(value, (int, float)) or not float("-inf") < float(value) < float("inf"):
            raise ValueError("gauge_value_invalid")
        with contextlib.closing(self.connect()) as connection, connection:
            connection.execute(
                "INSERT INTO gauges(name,value,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                (name, float(value), int(time.time())),
            )
        self.write_metrics()

    @contextlib.contextmanager
    def operation(self, module: str, action: str, correlation_id: str | None = None):
        module = self._name(module, "module")
        correlation_id = correlation_id or uuid.uuid4().hex
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{8,120}", correlation_id):
            raise ValueError("correlation_id_invalid")
        started = time.monotonic()
        self.log("info", module, "Operation started.", correlationId=correlation_id, action=action)
        try:
            yield correlation_id
        except Exception as error:
            latency = round((time.monotonic() - started) * 1000, 1)
            self.increment(f"{module}_failure")
            self.set_gauge(f"{module}_latency_ms", latency)
            self.log("error", module, "Operation failed.", correlationId=correlation_id, action=action, error=str(error), latencyMs=latency)
            raise
        else:
            latency = round((time.monotonic() - started) * 1000, 1)
            self.increment(f"{module}_success")
            self.set_gauge(f"{module}_latency_ms", latency)
            self.log("info", module, "Operation completed.", correlationId=correlation_id, action=action, latencyMs=latency)

    def write_metrics(self) -> None:
        with contextlib.closing(self.connect()) as connection, connection:
            rows = connection.execute("SELECT name,value FROM counters ORDER BY name").fetchall()
            circuits = connection.execute("SELECT name,state,failures FROM circuits ORDER BY name").fetchall()
            gauges = connection.execute("SELECT name,value FROM gauges ORDER BY name").fetchall()
        lines = [
            "# Nemotron local automation metrics. No prompts, outputs, paths, or secrets.",
            "# TYPE nemotron_automation_total counter",
        ]
        for row in rows:
            lines.append(f'nemotron_automation_total{{name="{row["name"]}"}} {row["value"]}')
        lines.append("# TYPE nemotron_circuit_failures gauge")
        for row in circuits:
            lines.append(f'nemotron_circuit_failures{{name="{row["name"]}",state="{row["state"]}"}} {row["failures"]}')
        lines.append("# TYPE nemotron_automation_gauge gauge")
        for row in gauges:
            lines.append(f'nemotron_automation_gauge{{name="{row["name"]}"}} {row["value"]}')
        atomic_write(self.metrics_path, ("\n".join(lines) + "\n").encode())


def retry(
    operation: Callable[[], T],
    *,
    attempts: int,
    retry_safe: bool,
    retryable: Callable[[Exception], bool],
    base_seconds: float = 1.0,
    maximum_seconds: float = 16.0,
    sleeper: Callable[[float], None] = time.sleep,
    random_source: Callable[[], float] = random.random,
) -> T:
    if not 1 <= attempts <= 6:
        raise ValueError("attempts_invalid")
    if attempts > 1 and not retry_safe:
        raise ValueError("retry_safety_required")
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as error:
            last_error = error
            if attempt == attempts or not retryable(error):
                raise
            delay = min(maximum_seconds, base_seconds * (2 ** (attempt - 1)))
            sleeper(delay * (0.75 + random_source() * 0.5))
    assert last_error is not None
    raise last_error


@contextlib.contextmanager
def wake_lock(
    enabled: bool,
    acquire: str = "/data/data/com.termux/files/usr/bin/termux-wake-lock",
    release: str = "/data/data/com.termux/files/usr/bin/termux-wake-unlock",
) -> Iterator[bool]:
    if not enabled:
        yield False
        return
    result = subprocess.run([acquire], capture_output=True, text=True, timeout=10, check=False)
    if result.returncode != 0:
        raise RuntimeError("wake_lock_acquire_failed")
    try:
        yield True
    finally:
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            subprocess.run([release], capture_output=True, text=True, timeout=10, check=False)
