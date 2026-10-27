r"""
STEP 3: The web app. Shows your jobs ranked, lets you filter them, refresh
for new listings, and mark jobs as saved, applied, or skipped.

Start it by double-clicking open-app.bat, or run:
    .venv\Scripts\python.exe -m streamlit run app.py
"""

import json
import re
from urllib.parse import urlparse

import streamlit as st

import apply_links
import config
import db
import fetch_jobs
import score_jobs
import settings_page
import usage
from fetch_jobs import format_salary

st.set_page_config(page_title="Job Finder", page_icon="💼", layout="wide")

SORTS = {"Apply First": "apply_score", "Fit": "fit_score", "Pay": "pay_score"}
PAGE_SIZE = 25


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def md(text):
    """Escape text so Streamlit shows it as-is ($ signs would otherwise turn into math)."""
    return re.sub(r"([\\`*_\[\]<>#|$~])", r"\\\1", text or "")


def change_status(job_id, status):
    """Button callback: saves the new status before the page redraws."""
    conn = db.connect()
    db.set_status(conn, job_id, status)
    conn.close()


def load_jobs(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM jobs")]


SOURCE_LABELS = {"company": "Company job boards", "jsearch": "Job sites (JSearch)",
                 "usajobs": "Government (USAJobs)"}


def passes_filters(job, work_types, hybrid_max, onsite_max, sources):
    """Your filter choices at the top of the page."""
    if SOURCE_LABELS.get(job["source"], job["source"]) not in sources:
        return False
    if job["work_type"] not in work_types:
        return False
    d = job["distance_mi"]
    if job["work_type"] == "hybrid" and d is not None and d > hybrid_max:
        return False
    if job["work_type"] == "on-site" and d is not None and d > onsite_max:
        return False
    return True


def sort_jobs(jobs, column):
    # Jobs with no score (e.g. no salary when sorting by pay) go to the bottom.
    return sorted(jobs, key=lambda j: (j[column] is None, -(j[column] or 0), -(j["fit_score"] or 0)))


# ---------------------------------------------------------------------------
# One job card
# ---------------------------------------------------------------------------

def show_job(job, tab):
    with st.container(border=True):
        left, middle, right = st.columns([6, 2, 2])

        with left:
            new_tag = "🆕 " if job["first_seen"] == st.session_state.get("latest_batch") else ""
            st.markdown(f"#### {new_tag}{md(job['title'])}")
            dist = f", {job['distance_mi']:.0f} mi" if job["distance_mi"] is not None else ""
            st.markdown(
                f"**{md(job['company'])}** · {md(job['location'])} ({job['work_type']}{dist}) · "
                f"{md(format_salary(job))}"
            )
            if job["fit_reason"]:
                st.caption(f"{md(job['fit_reason'])}  \nBest resume: **{md(job['best_resume'])}**")

        with middle:
            if job["apply_score"] is not None:
                st.metric("Apply First", f"{job['apply_score']:.0f}")
                pay = "–" if job["pay_score"] is None else f"{job['pay_score']:.0f}"
                st.caption(f"Fit **{job['fit_score']:.0f}** · Pay **{pay}**")
            else:
                st.caption("Not scored yet")

        with right:
            if job["company_url"]:
                st.link_button("🏢 Apply on company site", job["company_url"],
                               type="primary", use_container_width=True)
            else:
                # No company link known: search Google for the company's own posting.
                st.link_button("🔍 Find company posting", apply_links.search_url(job),
                               type="primary", use_container_width=True,
                               help="Searches Google for this job on the company's careers page")
            if job["url"] and job["url"] != job["company_url"]:
                site = (urlparse(job["url"]).hostname or "listing").removeprefix("www.")
                st.link_button(f"Open on {site} ↗", job["url"], use_container_width=True)
            actions = {
                "new": [("⭐ Save", "saved"), ("✅ Applied", "applied"), ("✖ Skip", "skipped")],
                "saved": [("✅ Applied", "applied"), ("↩ Unsave", "new"), ("✖ Skip", "skipped")],
                "applied": [("↩ Undo applied", "saved")],
                "skipped": [("↩ Restore", "new")],
            }[job["status"]]
            for label, status in actions:
                st.button(label, key=f"{tab}-{status}-{job['id']}", use_container_width=True,
                          on_click=change_status, args=(job["id"], status))

        with st.expander("Full description"):
            others = json.loads(job["apply_options"] or "[]")
            if others:
                st.markdown("**Also posted on:** " + " · ".join(
                    f"[{md(o['publisher'] or 'link')}]({o['apply_link']})" for o in others))
            st.markdown(md(job["description"]).replace("\n", "  \n") or "No description.")


def show_list(jobs, tab, empty_message):
    if not jobs:
        st.info(empty_message)
        return
    key = f"shown-{tab}"
    shown = st.session_state.get(key, PAGE_SIZE)
    for job in jobs[:shown]:
        show_job(job, tab)
    if len(jobs) > shown:
        if st.button(f"Show {min(PAGE_SIZE, len(jobs) - shown)} more", key=f"more-{tab}"):
            st.session_state[key] = shown + PAGE_SIZE
            st.rerun()


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------

conn = db.connect()

st.title("💼 Job Finder")

# First time (or "Settings" clicked): show the setup screen instead of the jobs.
if not config.IS_SET_UP or st.session_state.get("show_settings"):
    settings_page.show()
    st.stop()

if st.session_state.pop("just_set_up", False):
    st.success("You're all set! Hit **🔄 Refresh** to find your first jobs. "
               "The first search takes a few minutes while it downloads the AI model.")

# --- Request budget (sidebar) ---
with st.sidebar:
    st.subheader("JSearch requests")
    s = usage.jsearch_status(conn)
    per_refresh = len(config.TARGET_TITLES) * 2
    st.metric("Remaining this month", f"{s['remaining']} of {s['limit']}")
    st.progress(max(0.0, min(1.0, s["remaining"] / max(1, s["limit"]))))
    st.caption(
        f"A refresh uses {per_refresh} requests · "
        f"{usage.jsearch_calls_allowed(conn) // per_refresh} full refreshes left"
        + (f" · resets {s['reset_at']}" if s["reset_at"] else "")
        + f"  \n{config.JSEARCH_RESERVE} requests are always kept in reserve."
    )
    st.divider()
    st.caption(
        f"Home: {config.HOME_CITY}  \n"
        f"Hybrid jobs are searched within {config.HYBRID_MAX_MILES} mi, "
        f"on-site within {config.ONSITE_MAX_MILES} mi, remote anywhere in the US."
    )
    if st.button("⚙️ Settings", use_container_width=True):
        st.session_state["show_settings"] = True
        st.rerun()

# --- Filters and Refresh (top of page) ---
c1, c2, c3 = st.columns([3, 1, 1])
work_types = c1.multiselect("Work type", ["remote", "hybrid", "on-site"],
                            default=["remote", "hybrid", "on-site"])
# Narrowing options, up to the limits in your settings.
hybrid_options = sorted({m for m in (10, 25, 50, 75, 100) if m < config.HYBRID_MAX_MILES} | {config.HYBRID_MAX_MILES})
onsite_options = sorted({m for m in (10, 25, 40, 50) if m < config.ONSITE_MAX_MILES} | {config.ONSITE_MAX_MILES})
hybrid_max = c2.selectbox("Hybrid within", hybrid_options, index=len(hybrid_options) - 1,
                          format_func=lambda m: f"{m} miles")
onsite_max = c3.selectbox("On-site within", onsite_options, index=len(onsite_options) - 1,
                          format_func=lambda m: f"{m} miles")
sources = st.multiselect("Where jobs come from", list(SOURCE_LABELS.values()),
                         default=list(SOURCE_LABELS.values()))
c4, c5 = st.columns([3, 2], vertical_alignment="bottom")
sort_label = c4.radio("Sort by", list(SORTS), horizontal=True)
refresh_clicked = c5.button("🔄 Refresh", type="primary", use_container_width=True,
                            help=f"Search for new jobs (uses about {per_refresh} JSearch requests)")

if refresh_clicked:
    with st.status("Searching for new jobs...", expanded=True) as status:
        if usage.jsearch_calls_allowed(conn) < per_refresh:
            st.write("Not enough JSearch requests left for a full refresh, so only some titles will be searched.")
        result = fetch_jobs.refresh(conn)
        st.write(f"Found {result['found']} listings, {len(result['new_jobs'])} new. Scoring them against your resumes...")
        score_jobs.score_all(conn)
        status.update(label="Done", state="complete")
    st.session_state["last_refresh"] = result
    st.session_state["only_new"] = bool(result["new_jobs"])  # show what changed first
    st.rerun()

if "last_refresh" in st.session_state:
    r = st.session_state["last_refresh"]
    st.success(
        f"Refresh complete: {r['found']} listings found, {r['blocked']} blocked as spam or gig work, "
        f"{r['kept']} fit your location rules, **{len(r['new_jobs'])} new**."
    )
    for w in r["warnings"]:
        (st.info if w.startswith("Tip:") else st.warning)(w)

# --- The job lists ---
jobs = [j for j in load_jobs(conn) if passes_filters(j, work_types, hybrid_max, onsite_max, sources)]
column = SORTS[sort_label]
by_status = {s: sort_jobs([j for j in jobs if j["status"] == s], column)
             for s in ("new", "saved", "applied", "skipped")}

tabs = st.tabs([
    f"To review ({len(by_status['new'])})",
    f"⭐ Saved ({len(by_status['saved'])})",
    f"✅ Applied ({len(by_status['applied'])})",
    f"✖ Skipped ({len(by_status['skipped'])})",
])

with tabs[0]:
    # One list, best match first. Jobs from your most recent refresh are tagged 🆕,
    # and the switch shows only those (it turns on by itself after a Refresh).
    latest = max((j["first_seen"] for j in jobs), default=None)
    st.session_state["latest_batch"] = latest
    newest = [j for j in by_status["new"] if j["first_seen"] == latest]
    only_new = st.toggle(f"🆕 Only show the {len(newest)} new jobs from your last refresh", key="only_new")
    show_list(newest if only_new else by_status["new"], "review",
              "No new jobs from your last refresh." if only_new
              else "No jobs to review. Hit Refresh to look for new ones.")

with tabs[1]:
    show_list(by_status["saved"], "saved", "Jobs you save show up here.")
with tabs[2]:
    show_list(by_status["applied"], "applied", "Jobs you mark as applied show up here.")
with tabs[3]:
    st.caption("Skipped jobs never come back in your lists. Restore one if you change your mind.")
    show_list(by_status["skipped"], "skipped", "Nothing skipped.")
