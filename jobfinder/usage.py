"""
Keeps track of how many API requests you've used this month, so you never
run out or go over the free JSearch plan.

Two numbers are tracked:
  1. Our own count of calls made this calendar month.
  2. The "requests remaining" number JSearch sends back with every response.
     This one is the most accurate, so we trust it whenever we have it.

Run this file on its own to see where you stand:
    python jobfinder/usage.py
"""

from datetime import datetime, timedelta, timezone

import config
import db


def this_month():
    return datetime.now().strftime("%Y-%m")


def record_call(conn, source, headers=None):
    """
    Call this after every API request. `headers` are the HTTP response
    headers; JSearch (via RapidAPI) includes the remaining-request count in them.
    """
    month = this_month()
    conn.execute(
        "INSERT OR IGNORE INTO api_usage (source, month, calls) VALUES (?, ?, 0)",
        (source, month),
    )
    conn.execute(
        "UPDATE api_usage SET calls = calls + 1, updated_at = ? WHERE source = ? AND month = ?",
        (db.now_utc(), source, month),
    )

    # RapidAPI sends these headers on every response.
    if headers:
        limit = headers.get("x-ratelimit-requests-limit")
        remaining = headers.get("x-ratelimit-requests-remaining")
        reset_seconds = headers.get("x-ratelimit-requests-reset")
        if limit is not None and remaining is not None:
            reset_at = None
            if reset_seconds and reset_seconds.isdigit():
                reset_at = (
                    datetime.now(timezone.utc) + timedelta(seconds=int(reset_seconds))
                ).strftime("%Y-%m-%d")
            conn.execute(
                """
                UPDATE api_usage SET limit_reported = ?, remaining = ?, reset_at = ?
                WHERE source = ? AND month = ?
                """,
                (int(limit), int(remaining), reset_at, source, month),
            )
    conn.commit()


def jsearch_status(conn):
    """
    Returns a dict describing JSearch usage:
      used, limit, remaining, reset_at, and whether the numbers came from
      JSearch itself ("reported") or from our own count ("estimated").
    """
    row = conn.execute(
        "SELECT * FROM api_usage WHERE source = 'jsearch' AND month = ?",
        (this_month(),),
    ).fetchone()
    used = row["calls"] if row else 0

    if row and row["remaining"] is not None:
        return {
            "used": row["limit_reported"] - row["remaining"],
            "limit": row["limit_reported"],
            "remaining": row["remaining"],
            "reset_at": row["reset_at"],
            "basis": "reported",
        }
    return {
        "used": used,
        "limit": config.JSEARCH_MONTHLY_LIMIT,
        "remaining": config.JSEARCH_MONTHLY_LIMIT - used,
        "reset_at": None,
        "basis": "estimated",
    }


def jsearch_calls_allowed(conn):
    """How many more JSearch calls we can make right now without dipping into the reserve."""
    return max(0, jsearch_status(conn)["remaining"] - config.JSEARCH_RESERVE)


def print_status(conn):
    s = jsearch_status(conn)
    per_refresh = len(config.TARGET_TITLES) * 2
    print("JSearch requests")
    print(f"  Used this month : {s['used']}")
    print(f"  Remaining       : {s['remaining']} of {s['limit']}"
          + ("" if s["basis"] == "reported" else "  (estimate until the first real request)"))
    if s["reset_at"]:
        print(f"  Resets on       : {s['reset_at']}")
    print(f"  Safety reserve  : {config.JSEARCH_RESERVE} (never used)")
    print(f"  A full refresh  : {per_refresh} requests")
    print(f"  Full refreshes left: {jsearch_calls_allowed(conn) // per_refresh}")

    row = conn.execute(
        "SELECT calls FROM api_usage WHERE source = 'usajobs' AND month = ?",
        (this_month(),),
    ).fetchone()
    print(f"\nUSAJobs requests this month: {row['calls'] if row else 0} (free, no monthly limit)")


if __name__ == "__main__":
    print_status(db.connect())
