"""REST API endpoints for victron-bm-webui."""

import time
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")

# App start time for uptime calculation
_start_time = time.time()


@api_bp.route("/status")
def status():
    """Return current device state.

    Response:
        {
            "device_name": "BMV-712 Smart",
            "connected": true,
            "last_update": "2026-03-14T10:23:45+00:00",
            "voltage": 13.91,
            "current": -2.35,
            "power": -32.69,
            "soc": 85.0,
            "consumed_ah": -15.2,
            "remaining_mins": 388,
            "temperature": 18.0,
            "alarm": null
        }
    """
    shared_state = current_app.config.get("SHARED_STATE")
    if shared_state is None:
        return jsonify({"error": "Service not ready"}), 503

    config = current_app.config["VICTRON"]
    data = shared_state.get()
    data["device_name"] = config["device"].get("name", "BMV-712 Smart")

    return jsonify(data)


@api_bp.route("/history")
def history():
    """Return historical readings with optional filtering and downsampling.

    Query parameters:
        from: ISO 8601 start timestamp (inclusive)
        to: ISO 8601 end timestamp (inclusive)
        fields: comma-separated list of fields to return
        resolution: raw, 1min, 5min, 15min, 1h (default: raw)

    Response:
        {
            "readings": [...],
            "count": 100,
            "resolution": "raw"
        }
    """
    db = current_app.config["DB"]

    from_ts = request.args.get("from")
    to_ts = request.args.get("to")
    fields_param = request.args.get("fields")
    resolution = request.args.get("resolution", "raw")

    fields = None
    if fields_param:
        fields = [f.strip() for f in fields_param.split(",") if f.strip()]

    readings = db.get_readings_range(from_ts=from_ts, to_ts=to_ts, fields=fields)

    # Downsample if requested
    if resolution != "raw" and readings:
        readings = _downsample(readings, resolution)

    return jsonify({
        "readings": readings,
        "count": len(readings),
        "resolution": resolution,
    })


@api_bp.route("/alarms")
def alarms():
    """Return alarm log entries.

    Query parameters:
        from: ISO 8601 start timestamp (inclusive)
        to: ISO 8601 end timestamp (inclusive)
        limit: max entries to return (default: 100)

    Response:
        {
            "alarms": [...],
            "count": 5
        }
    """
    db = current_app.config["DB"]

    from_ts = request.args.get("from")
    to_ts = request.args.get("to")
    limit = request.args.get("limit", 100, type=int)
    limit = max(1, min(limit, 1000))

    alarm_list = db.get_alarms(from_ts=from_ts, to_ts=to_ts, limit=limit)

    return jsonify({
        "alarms": alarm_list,
        "count": len(alarm_list),
    })


@api_bp.route("/health")
def health():
    """Health check endpoint.

    Response:
        {
            "status": "ok",
            "uptime_seconds": 3600,
            "database": {"readings_count": 500, "alarms_count": 3, "size_bytes": 65536},
            "ble": {"connected": true, "mode": "mock"},
            "timestamp": "2026-03-14T10:23:45+00:00"
        }
    """
    db = current_app.config["DB"]
    shared_state = current_app.config.get("SHARED_STATE")
    config = current_app.config["VICTRON"]

    state = shared_state.get() if shared_state else {}
    mock_mode = config["device"].get("mock", False)

    return jsonify({
        "status": "ok",
        "uptime_seconds": round(time.time() - _start_time),
        "database": {
            "readings_count": db.get_reading_count(),
            "alarms_count": db.get_alarm_count(),
            "size_bytes": db.get_db_size(),
        },
        "ble": {
            "connected": state.get("connected", False),
            "mode": "mock" if mock_mode else "ble",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@api_bp.route("/config")
def config_info():
    """Return safe configuration info (no secrets).

    Response:
        {
            "smtp_enabled": true,
            "smtp_recipients": ["user@example.com"],
            "alarms": {"low_voltage": 11.5, ...}
        }
    """
    config = current_app.config["VICTRON"]
    smtp = config.get("smtp", {})
    alarms = config.get("alarms", {})

    return jsonify({
        "smtp_enabled": smtp.get("enabled", False),
        "smtp_recipients": smtp.get("recipients", []),
        "alarms": alarms,
    })


def _downsample(readings: list[dict], resolution: str) -> list[dict]:
    """Downsample readings by averaging within time buckets.

    Args:
        readings: List of reading dicts sorted by timestamp ASC.
        resolution: One of 1min, 5min, 15min, 1h.

    Returns:
        Downsampled list of reading dicts.
    """
    bucket_seconds = {
        "1min": 60,
        "5min": 300,
        "15min": 900,
        "1h": 3600,
    }
    interval = bucket_seconds.get(resolution)
    if interval is None:
        return readings

    numeric_fields = [
        "voltage", "current", "power", "soc",
        "consumed_ah", "remaining_mins", "temperature",
    ]

    result = []
    bucket: list[dict] = []
    bucket_start: float | None = None

    for reading in readings:
        try:
            ts = datetime.fromisoformat(reading["timestamp"]).timestamp()
        except (ValueError, KeyError):
            continue

        if bucket_start is None:
            bucket_start = ts

        if ts - bucket_start >= interval and bucket:
            result.append(_average_bucket(bucket, numeric_fields))
            bucket = []
            bucket_start = ts

        bucket.append(reading)

    if bucket:
        result.append(_average_bucket(bucket, numeric_fields))

    return result


def _average_bucket(bucket: list[dict], fields: list[str]) -> dict:
    """Average numeric fields in a bucket of readings."""
    averaged: dict = {"timestamp": bucket[0]["timestamp"]}

    for field in fields:
        values = [r[field] for r in bucket if field in r and r[field] is not None]
        if values:
            avg = sum(values) / len(values)
            if field == "remaining_mins":
                averaged[field] = round(avg)
            else:
                averaged[field] = round(avg, 2)
        elif field in bucket[0]:
            averaged[field] = None

    # Keep last alarm value from the bucket
    if "alarm" in bucket[-1]:
        averaged["alarm"] = bucket[-1]["alarm"]

    return averaged
