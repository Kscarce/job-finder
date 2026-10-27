"""
JSearch (on RapidAPI): private-sector jobs from Indeed, LinkedIn, Glassdoor
and others. Free plan, limited requests per month, so every call goes
through the budget check in usage.py.

Every source returns jobs as dicts with these keys:
    id, dedupe_key, source, title, company, location, city, country,
    work_type, distance_mi, salary_min, salary_max, salary_period,
    description, url, posted_at, search_title
"""

import os

import requests

import apply_links
import config
import location
import usage

NAME = "jsearch"
URL = "https://jsearch.p.rapidapi.com/search-v2"   # the old "/search" path no longer exists
KM_PER_MILE = 1.609


class OutOfRequests(Exception):
    """Raised instead of making a call that would dip into the safety reserve."""


def is_configured():
    return bool(os.getenv("JSEARCH_API_KEY"))


def _call(conn, params):
    """Make one request, after checking the monthly budget."""
    if usage.jsearch_calls_allowed(conn) <= 0:
        raise OutOfRequests()

    resp = requests.get(
        URL,
        headers={
            "X-RapidAPI-Key": os.getenv("JSEARCH_API_KEY"),
            "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
        },
        params=params,
        timeout=90,  # JSearch can be slow (often 10+ seconds)
    )
    # Count the call unless RapidAPI rejected it before it reached JSearch
    # (a 404 "endpoint does not exist" isn't charged).
    if resp.status_code != 404:
        usage.record_call(conn, NAME, resp.headers)

    if resp.status_code == 429:
        raise OutOfRequests()
    resp.raise_for_status()
    data = resp.json().get("data", [])
    # search-v2 returns {"jobs": [...], "cursor": ...}; older versions returned a plain list.
    return data.get("jobs", []) if isinstance(data, dict) else data


def fetch(title, conn):
    """Two searches per title: one around home, one for remote jobs anywhere in the US."""
    jobs = []

    # 1) Jobs near home (we filter hybrid vs on-site distances afterwards).
    local = _call(conn, {
        "query": f"{title} in {config.HOME_CITY}",
        "radius": round(config.SEARCH_RADIUS_MILES * KM_PER_MILE),  # JSearch wants km
        "country": "us",
        "page": 1,
        "num_pages": 1,
        "date_posted": config.JSEARCH_DATE_POSTED,
    })
    jobs += [_to_job(raw, title) for raw in local]

    # 2) Remote jobs anywhere in the US.
    remote = _call(conn, {
        "query": f"{title} remote",
        "work_from_home": "true",
        "country": "us",
        "page": 1,
        "num_pages": 1,
        "date_posted": config.JSEARCH_DATE_POSTED,
    })
    jobs += [_to_job(raw, title, searched_remote=True) for raw in remote]
    return jobs


def _to_job(raw, search_title, searched_remote=False):
    """Convert one JSearch result into our standard job format."""
    title = raw.get("job_title") or ""
    company = raw.get("employer_name") or ""
    city = raw.get("job_city") or ""
    state = raw.get("job_state") or ""
    description = raw.get("job_description") or ""
    # JSearch also sends bullet lists pulled from the posting. Qualifications is
    # often where "3+ years of experience" lives, so keep it for scoring.
    highlights = raw.get("job_highlights") or {}
    for heading in ("Qualifications", "Responsibilities"):
        items = highlights.get(heading) or []
        if items:
            description += f"\n\n{heading}:\n" + "\n".join(f"• {i}" for i in items)

    work_type = location.detect_work_type(
        title, description, api_says_remote=bool(raw.get("job_is_remote"))
    )
    # Remote jobs have no meaningful distance. When there's no city, JSearch's
    # coordinates are just the middle of the state, so the distance would be wrong.
    distance = None
    if work_type != "remote" and city:
        distance = location.miles_from_home(raw.get("job_latitude"), raw.get("job_longitude"))
    place = (raw.get("job_location") or ", ".join(p for p in (city, state) if p)
             or ("Remote" if searched_remote else ""))

    return {
        "id": f"{NAME}:{raw.get('job_id')}",
        "dedupe_key": location.make_dedupe_key(title, company, city),
        "source": NAME,
        "title": title,
        "company": company,
        "location": place,
        "city": city,
        "country": raw.get("job_country") or "US",
        "work_type": work_type,
        "distance_mi": distance,
        "salary_min": raw.get("job_min_salary"),
        "salary_max": raw.get("job_max_salary"),
        "salary_period": raw.get("job_salary_period"),
        "description": description,
        "url": raw.get("job_apply_link") or raw.get("job_google_link"),
        "company_url": (raw.get("job_apply_link") if raw.get("job_apply_is_direct")
                        else apply_links.pick_company_link(raw.get("apply_options"), company)),
        "apply_options": apply_links.options_json(raw.get("apply_options")),
        "posted_at": raw.get("job_posted_at_datetime_utc"),
        "search_title": search_title,
    }
