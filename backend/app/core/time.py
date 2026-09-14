"""Timezone and timestamp helpers.

All backend timestamps are stored as naive UTC datetimes (authoritative).
Operational dates are computed in the configured app timezone (Asia/Riyadh).
"""
from __future__ import annotations

import datetime as dt
import zoneinfo

from app.core.config import settings

APP_TZ = zoneinfo.ZoneInfo(settings.app_timezone)


def now_utc() -> dt.datetime:
    """Current time as a naive UTC datetime (authoritative, stored form)."""
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def today_local() -> dt.date:
    """Operational service date in the app timezone."""
    return dt.datetime.now(APP_TZ).date()


def local_date_of(naive_utc: dt.datetime) -> dt.date:
    """Map a naive-UTC datetime to its date in the app timezone."""
    if naive_utc.tzinfo is not None:
        naive_utc = naive_utc.replace(tzinfo=None)
    return naive_utc.replace(tzinfo=dt.timezone.utc).astimezone(APP_TZ).date()


def utc_now_iso() -> str:
    return now_utc().isoformat(sep=" ")


def classify_arrival(arrival_at: dt.datetime, earliest_scheduled: dt.datetime) -> str:
    """Classify a scheduled visit as EARLY / LATE / SCHEDULED vs threshold minutes."""
    early = settings.early_threshold_minutes
    late = settings.late_threshold_minutes
    delta = (arrival_at - earliest_scheduled).total_seconds() / 60.0
    if delta < -early:
        return "EARLY"
    if delta > late:
        return "LATE"
    return "SCHEDULED"
