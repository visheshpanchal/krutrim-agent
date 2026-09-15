"""Date/time tools shared across agent profiles."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langchain_core.tools import tool


def _resolve_timezone(timezone: str | None):
    """Return a ZoneInfo for the given name, or the system's local timezone if None."""
    if timezone is None:
        return datetime.now().astimezone().tzinfo
    return ZoneInfo(timezone)


@tool
def datetime_tool(timezone: str | None = None) -> str:
    """Get the current date and time (ISO 8601), including UTC offset.

    Args:
        timezone: Optional IANA timezone name, e.g. "America/New_York".
            If omitted, uses the system's local timezone.
    """
    try:
        tz = _resolve_timezone(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return f"Error: unknown timezone '{timezone}'"
    return datetime.now(tz).isoformat()
