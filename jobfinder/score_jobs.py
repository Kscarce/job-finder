"""
STEP 2: Score every saved job against your resumes and print them ranked.

Run it with:
    python jobfinder/score_jobs.py              (ranked by Apply First)
    python jobfinder/score_jobs.py fit          (ranked by fit)
    python jobfinder/score_jobs.py pay          (ranked by pay)
    python jobfinder/score_jobs.py apply 50     (show the top 50 instead of 25)
"""

import sys

import blocklist
import db
import scoring
from fetch_jobs import format_salary

SORTS = {"apply": "apply_score", "fit": "fit_score", "pay": "pay_score"}


def score_all(conn):
    """Scores every job you haven't skipped and saves the scores. Returns how many."""
    jobs = [dict(r) for r in conn.execute("SELECT * FROM jobs WHERE status != 'skipped'")]

    # Jobs saved before you added something to the blocklist are removed here.
    for job in [j for j in jobs if blocklist.blocked_reason(j)]:
        conn.execute("DELETE FROM jobs WHERE id = ?", (job["id"],))
        jobs.remove(job)
    conn.commit()

    if not jobs:
        return 0
    results = scoring.score_jobs(jobs)
    now = db.now_utc()
    for job_id, r in results.items():
        conn.execute(
            """
            UPDATE jobs SET fit_score = ?, fit_reason = ?, best_resume = ?,
                            pay_score = ?, apply_score = ?, scored_at = ?
            WHERE id = ?
            """,
            (r["fit_score"], r["fit_reason"], r["best_resume"], r["pay_score"],
             r["apply_score"], now, job_id),
        )
    conn.commit()
    return len(results)


def print_ranked(conn, sort="apply", limit=25):
    column = SORTS.get(sort, "apply_score")
    rows = conn.execute(
        f"""
        SELECT * FROM jobs WHERE status != 'skipped' AND fit_score IS NOT NULL
        ORDER BY {column} IS NULL, {column} DESC, fit_score DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()

    print(f"\nTop {len(rows)} jobs by {sort}:")
    for i, job in enumerate(rows, 1):
        dist = "" if job["distance_mi"] is None else f", {job['distance_mi']:.0f} mi"
        pay = "" if job["pay_score"] is None else f"  Pay {job['pay_score']:.0f}"
        print(f"\n{i:2}. {job['title']}  |  {job['company']}")
        print(f"    Apply First {job['apply_score']:.0f}  Fit {job['fit_score']:.0f}{pay}"
              f"  |  best resume: {job['best_resume']}")
        print(f"    {job['fit_reason']}")
        print(f"    {job['location']} ({job['work_type']}{dist})  |  {format_salary(job)}")
        print(f"    {job['url']}")


if __name__ == "__main__":
    import config
    if not config.IS_SET_UP:
        raise SystemExit("Not set up yet: open the app (open-app.bat) and fill in the setup screen first.")
    sort = sys.argv[1] if len(sys.argv) > 1 else "apply"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 25
    conn = db.connect()
    print("Scoring jobs against your resumes (the first run downloads the AI model, ~90 MB)...")
    print(f"Scored {score_all(conn)} jobs.")
    print_ranked(conn, sort, limit)
