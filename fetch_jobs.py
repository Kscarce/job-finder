"""
STEP 1: Pull job listings from every source, apply your location rules,
remove duplicates, save them to the database, and print the new ones.

Run it with:
    python fetch_jobs.py
"""

from dotenv import load_dotenv

import blocklist
import config
import db
import location
import usage
from sources import SOURCES, jsearch


def fetch_all(conn):
    """Search every source for every target title. Returns (jobs, warnings)."""
    jobs, warnings = [], []

    for source in SOURCES:
        if not source.is_configured():
            warnings.append(f"{source.NAME}: no API key in keys/.env, skipped.")
            continue

        # Sources that download everything at once (company job boards).
        if hasattr(source, "fetch_everything"):
            try:
                found = source.fetch_everything(conn)
                print(f"  {source.NAME:8} {'all company boards':30} {len(found):3} results")
                jobs += found
            except Exception as e:
                warnings.append(f"{source.NAME}: failed: {e}")
            continue

        for title in config.TARGET_TITLES:
            # Each JSearch title costs 2 requests. Stop before going over budget.
            if source is jsearch and usage.jsearch_calls_allowed(conn) < 2:
                warnings.append(
                    f"jsearch: stopped before '{title}' to stay within your monthly "
                    f"request limit (keeping {config.JSEARCH_RESERVE} in reserve)."
                )
                break
            try:
                found = source.fetch(title, conn)
                print(f"  {source.NAME:8} {title:30} {len(found):3} results")
                jobs += found
            except jsearch.OutOfRequests:
                warnings.append("jsearch: out of requests for this month, stopped.")
                break
            except Exception as e:  # one failed search shouldn't stop the rest
                warnings.append(f"{source.NAME}: '{title}' failed: {e}")
    return jobs, warnings


def filter_and_dedupe(jobs):
    """
    Drop blocked jobs, apply your remote / hybrid / on-site distance rules,
    and drop duplicates. Returns (kept jobs, number blocked).
    """
    kept, seen, blocked = [], set(), 0
    for job in jobs:
        if blocklist.blocked_reason(job):
            blocked += 1
            continue
        if not location.passes_location_rules(job["work_type"], job["distance_mi"], job["country"]):
            continue
        if job["id"] in seen or job["dedupe_key"] in seen:
            continue
        seen.update((job["id"], job["dedupe_key"]))
        kept.append(job)
    return kept, blocked


def format_salary(job):
    lo, hi, period = job["salary_min"], job["salary_max"], job["salary_period"]
    if not lo and not hi:
        return "Not listed"
    per = {"YEAR": "/yr", "HOUR": "/hr", "MONTH": "/mo"}.get(period or "", "")
    if lo and hi and lo != hi:
        return f"${lo:,.0f} - ${hi:,.0f}{per}"
    return f"${(lo or hi):,.0f}{per}"


def print_jobs(jobs):
    for job in jobs:
        dist = "" if job["distance_mi"] is None else f", {job['distance_mi']:.0f} mi"
        if job["work_type"] != "remote" and job["distance_mi"] is None:
            dist = ", distance unknown"
        print(f"\n{job['title']}  |  {job['company']}")
        print(f"  {job['location']} ({job['work_type']}{dist})  |  {format_salary(job)}  |  {job['source']}")
        print(f"  {job['url']}")


def refresh(conn):
    """Search every source, filter, and save. Used by this script and by the web app."""
    load_dotenv(config.KEYS_FILE)
    raw, warnings = fetch_all(conn)
    jobs, blocked = filter_and_dedupe(raw)
    new_jobs = db.save_jobs(conn, jobs)
    return {"found": len(raw), "blocked": blocked, "kept": len(jobs),
            "new_jobs": new_jobs, "warnings": warnings}


def main():
    conn = db.connect()

    print("Before this run:")
    usage.print_status(conn)

    print("\nSearching...")
    result = refresh(conn)

    print_jobs(result["new_jobs"])

    print(f"\n{result['found']} results found, {result['blocked']} blocked as spam or gig work, "
          f"{result['kept']} passed your location rules after removing duplicates, "
          f"{len(result['new_jobs'])} are new since last time.")
    for w in result["warnings"]:
        print(f"WARNING: {w}")

    print("\nAfter this run:")
    usage.print_status(conn)


if __name__ == "__main__":
    main()
