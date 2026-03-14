"""SQLite database layer for victron-bm-webui."""

import sqlite3
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

log = logging.getLogger(__name__)

SCHEMA_READINGS = """
CREATE TABLE IF NOT EXISTS readings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,
    voltage         REAL,
    current         REAL,
    power           REAL,
    soc             REAL,
    consumed_ah     REAL,
    remaining_mins  INTEGER,
    temperature     REAL,
    alarm           TEXT
);
"""

SCHEMA_ALARM_LOG = """
CREATE TABLE IF NOT EXISTS alarm_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,
    alarm_type      TEXT    NOT NULL,
    message         TEXT,
    notified        INTEGER NOT NULL DEFAULT 0
);
"""

INDEX_READINGS_TS = """
CREATE INDEX IF NOT EXISTS idx_readings_timestamp ON readings (timestamp);
"""

INDEX_ALARM_LOG_TS = """
CREATE INDEX IF NOT EXISTS idx_alarm_log_timestamp ON alarm_log (timestamp);
"""


class Database:
    """SQLite database manager for readings and alarm log."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        """Create a new database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init(self) -> None:
        """Create tables and indexes if they don't exist."""
        conn = self._connect()
        try:
            conn.execute(SCHEMA_READINGS)
            conn.execute(SCHEMA_ALARM_LOG)
            conn.execute(INDEX_READINGS_TS)
            conn.execute(INDEX_ALARM_LOG_TS)
            conn.commit()
            log.info("Database initialized: %s", self.db_path)
        finally:
            conn.close()

    # -- Readings --

    def insert_reading(self, data: dict[str, Any]) -> None:
        """Insert a single reading into the database.

        Args:
            data: Dictionary with keys matching readings columns
                  (timestamp, voltage, current, power, soc,
                   consumed_ah, remaining_mins, temperature, alarm).
        """
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO readings
                   (timestamp, voltage, current, power, soc,
                    consumed_ah, remaining_mins, temperature, alarm)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    data.get("timestamp", datetime.now(timezone.utc).isoformat()),
                    data.get("voltage"),
                    data.get("current"),
                    data.get("power"),
                    data.get("soc"),
                    data.get("consumed_ah"),
                    data.get("remaining_mins"),
                    data.get("temperature"),
                    data.get("alarm"),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_recent_readings(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get the most recent readings.

        Args:
            limit: Maximum number of readings to return.

        Returns:
            List of reading dictionaries, newest first.
        """
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM readings ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_readings_range(
        self,
        from_ts: str | None = None,
        to_ts: str | None = None,
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Get readings within a time range.

        Args:
            from_ts: ISO 8601 start timestamp (inclusive).
            to_ts: ISO 8601 end timestamp (inclusive).
            fields: List of field names to return. None = all fields.

        Returns:
            List of reading dictionaries, oldest first.
        """
        allowed_fields = {
            "timestamp", "voltage", "current", "power", "soc",
            "consumed_ah", "remaining_mins", "temperature", "alarm",
        }
        if fields:
            safe_fields = [f for f in fields if f in allowed_fields]
            if not safe_fields:
                safe_fields = list(allowed_fields)
            select_cols = ", ".join(["timestamp"] + [f for f in safe_fields if f != "timestamp"])
        else:
            select_cols = "*"

        conditions = []
        params: list[Any] = []

        if from_ts:
            conditions.append("timestamp >= ?")
            params.append(from_ts)
        if to_ts:
            conditions.append("timestamp <= ?")
            params.append(to_ts)

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT {select_cols} FROM readings{where} ORDER BY timestamp ASC"

        conn = self._connect()
        try:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    # -- Alarm Log --

    def insert_alarm(self, alarm_type: str, message: str, notified: bool = False) -> None:
        """Insert an alarm log entry.

        Args:
            alarm_type: Alarm type identifier (e.g. LOW_VOLTAGE).
            message: Human-readable alarm message.
            notified: Whether email notification was sent.
        """
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO alarm_log (timestamp, alarm_type, message, notified)
                   VALUES (?, ?, ?, ?)""",
                (
                    datetime.now(timezone.utc).isoformat(),
                    alarm_type,
                    message,
                    1 if notified else 0,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_alarms(
        self,
        from_ts: str | None = None,
        to_ts: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get alarm log entries.

        Args:
            from_ts: ISO 8601 start timestamp (inclusive).
            to_ts: ISO 8601 end timestamp (inclusive).
            limit: Maximum number of entries to return.

        Returns:
            List of alarm dictionaries, newest first.
        """
        conditions = []
        params: list[Any] = []

        if from_ts:
            conditions.append("timestamp >= ?")
            params.append(from_ts)
        if to_ts:
            conditions.append("timestamp <= ?")
            params.append(to_ts)

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT * FROM alarm_log{where} ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        conn = self._connect()
        try:
            rows = conn.execute(query, params).fetchall()
            result = []
            for row in rows:
                d = dict(row)
                d["notified"] = bool(d["notified"])
                result.append(d)
            return result
        finally:
            conn.close()

    # -- Maintenance --

    def purge_old_readings(self, retention_days: int) -> int:
        """Delete readings older than the retention period.

        Args:
            retention_days: Number of days to keep.

        Returns:
            Number of rows deleted.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        conn = self._connect()
        try:
            cursor = conn.execute(
                "DELETE FROM readings WHERE timestamp < ?", (cutoff,)
            )
            conn.commit()
            deleted = cursor.rowcount
            if deleted > 0:
                log.info("Purged %d readings older than %d days", deleted, retention_days)
            return deleted
        finally:
            conn.close()

    def purge_old_alarms(self, retention_days: int) -> int:
        """Delete alarm log entries older than the retention period.

        Args:
            retention_days: Number of days to keep.

        Returns:
            Number of rows deleted.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        conn = self._connect()
        try:
            cursor = conn.execute(
                "DELETE FROM alarm_log WHERE timestamp < ?", (cutoff,)
            )
            conn.commit()
            deleted = cursor.rowcount
            if deleted > 0:
                log.info("Purged %d alarm log entries older than %d days", deleted, retention_days)
            return deleted
        finally:
            conn.close()

    def get_db_size(self) -> int:
        """Get the database file size in bytes."""
        import os
        try:
            return os.path.getsize(self.db_path)
        except OSError:
            return 0

    def get_reading_count(self) -> int:
        """Get total number of readings in the database."""
        conn = self._connect()
        try:
            row = conn.execute("SELECT COUNT(*) FROM readings").fetchone()
            return row[0] if row else 0
        finally:
            conn.close()

    def get_alarm_count(self) -> int:
        """Get total number of alarm log entries."""
        conn = self._connect()
        try:
            row = conn.execute("SELECT COUNT(*) FROM alarm_log").fetchone()
            return row[0] if row else 0
        finally:
            conn.close()
