"""
Looks up the company's own posting for jobs you already have, using JSearch's
job-details endpoint. Each job costs 1 JSearch request, so it only checks your
best-ranked jobs, and never dips into your request reserve.

Run it with:
    python find_company_links.py        (checks your top 10 jobs)
    python find_company_links.py 20     (checks your top 20)
"""

import os
import sys

import requests
from dotenv import load_dotenv

import apply_links
import config
import db
import usage

URL = "https://jsearch.p.rapidapi.com/job-details"


def look_up(conn, job_id):
    """Returns JSearch's details for one job, or None."""
    resp = requests.get(
        URL,
        headers={"X-RapidAPI-Key": os.getenv("JSEARCH_API_KEY"),
                 "X-RapidAPI-Host": "jsearch.p.rapidapi.com"},
        params={"job_id": job_id, "country": "us"},
        timeout=90,
    )
    if resp.status_code != 404:
        usage.record_call(conn, "jsearch", resp.headers)
    resp.raise_for_status()
    data = resp.json().get("data")
    if isinstance(data, dict):
        data = data.get("jobs") or [data]
    return data[0] if data else None


def main(limit):
    load_dotenv(config.KEYS_FILE)
    conn = db.connect()
    jobs = conn.execute(
        """
        SELECT id, title, company FROM jobs
        WHERE source = 'jsearch' AND company_url IS NULL AND apply_options IS NULL
              AND status IN ('new', 'saved')
        ORDER BY apply_score DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()

    found = 0
    for job in jobs:
        if usage.jsearch_calls_allowed(conn) <= 0:
            print("Stopped: no JSearch requests left outside your reserve.")
            break
        try:
            details = look_up(conn, job["id"].split(":", 1)[1])
        except Exception as e:
            print(f"  could not check {job['title'][:50]}: {e}")
            continue
        if not details:
            print(f"  no longer listed: {job['title'][:50]}")
            conn.execute("UPDATE jobs SET apply_options = '[]' WHERE id = ?", (job["id"],))
            continue

        options = details.get("apply_options")
        company_url = (details.get("job_apply_link") if details.get("job_apply_is_direct")
                       else apply_links.pick_company_link(options, job["company"]))
        conn.execute("UPDATE jobs SET company_url = ?, apply_options = ? WHERE id = ?",
                     (company_url, apply_links.options_json(options), job["id"]))
        conn.commit()
        found += bool(company_url)
        print(f"  {'FOUND' if company_url else 'none '}  {job['title'][:50]} | {job['company']}"
              + (f"\n         {company_url}" if company_url else ""))

    print(f"\nFound the company's own posting for {found} of {len(jobs)} jobs checked.")
    usage.print_status(conn)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10)
