"""
USAJobs: federal government jobs. Completely free, no monthly limit,
but we still count calls so you can see them in usage.py.
"""

import os

import requests

import config
import location
import usage

NAME = "usajobs"
URL = "https://data.usajobs.gov/api/search"

# USAJobs pay interval codes -> our standard names
PERIODS = {"PA": "YEAR", "PH": "HOUR", "PM": "MONTH", "BW": "BIWEEKLY"}


def is_configured():
    return bool(os.getenv("USAJOBS_API_KEY") and os.getenv("USAJOBS_EMAIL"))


def _call(conn, params):
    resp = requests.get(
        URL,
        headers={
            "Host": "data.usajobs.gov",
            "User-Agent": os.getenv("USAJOBS_EMAIL"),
            "Authorization-Key": os.getenv("USAJOBS_API_KEY"),
        },
        params=params,
        timeout=30,
    )
    usage.record_call(conn, NAME)
    resp.raise_for_status()
    return resp.json().get("SearchResult", {}).get("SearchResultItems", [])


def fetch(title, conn):
    """Two searches per title: around home, and remote jobs anywhere."""
    local = _call(conn, {
        "Keyword": title,
        "LocationName": config.HOME_CITY,
        "Radius": config.SEARCH_RADIUS_MILES,  # USAJobs uses miles
        "ResultsPerPage": 100,
    })
    remote = _call(conn, {
        "Keyword": title,
        "RemoteIndicator": "True",
        "ResultsPerPage": 100,
    })
    return [_to_job(item, title) for item in local + remote]


def _to_job(item, search_title):
    """Convert one USAJobs result into our standard job format."""
    d = item.get("MatchedObjectDescriptor", {})
    details = d.get("UserArea", {}).get("Details", {})

    title = d.get("PositionTitle") or ""
    company = d.get("OrganizationName") or d.get("DepartmentName") or ""

    # Federal jobs can list several locations; use the one closest to home.
    best = None
    for loc in d.get("PositionLocation", []):
        dist = location.miles_from_home(loc.get("Latitude"), loc.get("Longitude"))
        if dist is not None and (best is None or dist < best[0]):
            best = (dist, loc)
    distance, city = (best[0], best[1].get("CityName", "")) if best else (None, "")

    description = "\n\n".join(filter(None, [
        details.get("JobSummary"),
        "\n".join(details.get("MajorDuties") or []),
        d.get("QualificationSummary"),
    ]))

    work_type = location.detect_work_type(
        title, description,
        api_says_remote=str(details.get("RemoteIndicator")).lower() == "true",
        # Federal "telework eligible" usually means some days at home = hybrid.
        api_says_hybrid=str(details.get("TeleworkEligible")).lower() == "true",
    )
    if work_type == "remote":
        distance = None

    pay = (d.get("PositionRemuneration") or [{}])[0]

    return {
        "id": f"{NAME}:{d.get('PositionID') or item.get('MatchedObjectId')}",
        "dedupe_key": location.make_dedupe_key(title, company, city),
        "source": NAME,
        "title": title,
        "company": company,
        "location": city or d.get("PositionLocationDisplay", ""),
        "city": city,
        "country": "US",
        "work_type": work_type,
        "distance_mi": distance,
        "salary_min": _to_float(pay.get("MinimumRange")),
        "salary_max": _to_float(pay.get("MaximumRange")),
        "salary_period": PERIODS.get(pay.get("RateIntervalCode"), pay.get("RateIntervalCode")),
        "description": description,
        "url": d.get("PositionURI"),
        "company_url": d.get("PositionURI"),  # USAJobs is the government's own hiring site
        "apply_options": None,
        "posted_at": d.get("PublicationStartDate"),
        "search_title": search_title,
    }


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
