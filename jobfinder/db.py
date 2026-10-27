"""
The local SQLite database. It stores every job we've seen (so skipped or
old jobs don't come back) and how many API requests we've used.
"""

import sqlite3
from datetime import datetime, timezone

import config


def connect():
    """Open the database, creating the file and tables the first time."""
    config.DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(config.DB_FILE)
    conn.row_factory = sqlite3.Row  # lets us use row["title"] instead of row[0]
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id            TEXT PRIMARY KEY,   -- e.g. "jsearch:abc123"
            dedupe_key    TEXT UNIQUE,        -- title + company + city, to catch the same job from two sources
            source        TEXT,
            title         TEXT,
            company       TEXT,
            location      TEXT,
            work_type     TEXT,               -- remote / hybrid / on-site
            distance_mi   REAL,               -- miles from home, NULL if unknown
            salary_min    REAL,
            salary_max    REAL,
            salary_period TEXT,               -- YEAR / HOUR / MONTH
            description   TEXT,
            url           TEXT,
            posted_at     TEXT,
            search_title  TEXT,               -- which of your target titles found it
            first_seen    TEXT,
            status        TEXT DEFAULT 'new'  -- new / saved / applied / skipped
        );

        -- One row per API source per month.
        CREATE TABLE IF NOT EXISTS api_usage (
            source          TEXT,
            month           TEXT,     -- "2026-10"
            calls           INTEGER DEFAULT 0,
            limit_reported  INTEGER,  -- monthly limit the API told us about
            remaining       INTEGER,  -- requests left, as the API told us
            reset_at        TEXT,     -- when the API says the count resets
            updated_at      TEXT,
            PRIMARY KEY (source, month)
        );
        """
    )

    # Score columns (added in step 2). Older databases get them added here.
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
    for column, kind in [
        ("fit_score", "REAL"),      # 0-100, how well the job matches your resumes
        ("fit_reason", "TEXT"),     # plain-language reason for the score
        ("best_resume", "TEXT"),    # which of your resumes matched best
        ("pay_score", "REAL"),      # 0-100 vs. other jobs with the same title, NULL if no salary
        ("apply_score", "REAL"),    # the combined Apply First rank
        ("scored_at", "TEXT"),
        ("company_url", "TEXT"),    # the company's own posting, when we could find it
        ("apply_options", "TEXT"),  # every place the job is posted (JSON list)
    ]:
        if column not in existing:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {column} {kind}")
    conn.commit()
    return conn


def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def set_status(conn, job_id, status):
    """Mark a job as new, saved, applied, or skipped."""
    conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
    conn.commit()


def save_jobs(conn, jobs):
    """
    Insert jobs we haven't seen before. Jobs already in the database are left
    alone, so their saved/applied/skipped status is kept.
    Returns the list of jobs that were new this time.
    """
    new_jobs = []
    seen_at = now_utc()
    for job in jobs:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO jobs (
                id, dedupe_key, source, title, company, location, work_type,
                distance_mi, salary_min, salary_max, salary_period,
                description, url, posted_at, search_title, first_seen,
                company_url, apply_options
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job["id"], job["dedupe_key"], job["source"], job["title"],
                job["company"], job["location"], job["work_type"],
                job["distance_mi"], job["salary_min"], job["salary_max"],
                job["salary_period"], job["description"], job["url"],
                job["posted_at"], job["search_title"], seen_at,
                job.get("company_url"), job.get("apply_options"),
            ),
        )
        if cur.rowcount == 1:  # 1 means it was inserted, 0 means it was already there
            new_jobs.append(job)
    conn.commit()
    return new_jobs
