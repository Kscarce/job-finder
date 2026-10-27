"""
Company job boards: tech companies that post jobs through Greenhouse, Lever
or Ashby, which all have free public feeds. No key, no request limit, full
job descriptions, and every link goes straight to the company's own posting.

The list of companies is COMPANY_BOARDS in config.py.

Unlike the other sources, this one downloads each company's whole board once
per refresh and keeps the jobs matching your target titles, so it has a
fetch_everything() function instead of fetch(title).
"""

import html
import re
from concurrent.futures import ThreadPoolExecutor

import requests

import config
import geocode
import location
from scoring import SENIOR, normalize_title, target_words, title_matches_target

NAME = "company"

# Places that mean the job is outside the US.
FOREIGN = re.compile(
    r"canada|toronto|vancouver|montreal|united kingdom|\buk\b|london|dublin|ireland|"
    r"germany|berlin|munich|france|paris|netherlands|amsterdam|spain|madrid|poland|"
    r"india|bangalore|bengaluru|singapore|japan|tokyo|australia|sydney|brazil|"
    r"mexico|emea|apac|latam|europe|israel|tel aviv|korea|seoul|switzerland|zurich",
    re.IGNORECASE,
)
US = re.compile(r"\bus\b|\busa\b|u\.s\.|united states|north america|americas", re.IGNORECASE)


def is_configured():
    return True  # free, no key needed


def fetch_everything(conn):
    """Download every company board at once and keep the jobs that fit you."""
    boards = [(kind, name) for kind, names in config.COMPANY_BOARDS.items() for name in names]
    jobs = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        for found in pool.map(lambda b: _fetch_board(*b), boards):
            jobs += found
    # Greenhouse lists don't include descriptions, so fetch them only for the keepers.
    with ThreadPoolExecutor(max_workers=10) as pool:
        jobs = list(pool.map(_add_greenhouse_details, jobs))
    return jobs


def _fetch_board(kind, name):
    try:
        if kind == "greenhouse":
            data = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{name}/jobs",
                                timeout=30).json().get("jobs", [])
            return [j for j in (_from_greenhouse(raw, name) for raw in data) if j]
        if kind == "lever":
            data = requests.get(f"https://api.lever.co/v0/postings/{name}?mode=json", timeout=30).json()
            return [j for j in (_from_lever(raw, name) for raw in data) if j]
        if kind == "ashby":
            data = requests.get(f"https://api.ashbyhq.com/posting-api/job-board/{name}"
                                "?includeCompensation=true", timeout=30).json().get("jobs", [])
            return [j for j in (_from_ashby(raw, name) for raw in data) if j]
    except Exception as e:
        print(f"  company board {name} ({kind}) failed: {e}")
    return []


# ---------------------------------------------------------------------------
# Deciding which jobs to keep
# ---------------------------------------------------------------------------

def _wanted_title(title):
    if config.BOARDS_SKIP_SENIOR and re.search(SENIOR, title.lower()):
        return False
    return title_matches_target(title)


def _place(location_text, remote_flag=False, workplace=""):
    """
    Works out (work_type, distance_mi, city) from a board's location text.
    Returns None if the job is outside the US or too far away to matter.
    """
    loc = location_text or ""
    remote = remote_flag or "remote" in loc.lower() or workplace.lower() == "remote"
    if FOREIGN.search(loc) and not US.search(loc):
        return None
    if remote:
        return "remote", None, ""
    # Office jobs: look up each listed city and use the one closest to home.
    best = None
    for part in re.split(r";|\||/|\bor\b", loc):
        part = re.sub(r",?\s*(united states|usa|us)\.?$", "", part.strip(), flags=re.IGNORECASE)
        if not part or FOREIGN.search(part):
            continue
        spot = geocode.lookup(part)
        if spot:
            miles = location.miles_from_home(spot["lat"], spot["lon"])
            if best is None or miles < best[0]:
                best = (miles, part.split(",")[0].strip())
    if best is None or best[0] > config.SEARCH_RADIUS_MILES:
        return None  # an office outside your area
    wt = "hybrid" if workplace.lower() == "hybrid" else "on-site"
    return wt, best[0], best[1]


def _job(company_key, raw_id, title, company, loc_text, place, description, url,
         salary=(None, None, None), posted=None):
    work_type, distance, city = place
    # The board may only say "hybrid" in the description.
    if work_type == "on-site":
        work_type = location.detect_work_type(title, description)
        work_type = "on-site" if work_type == "remote" else work_type
    return {
        "id": f"{NAME}:{company_key}:{raw_id}",
        "dedupe_key": location.make_dedupe_key(title, company, city),
        "source": NAME,
        "title": title,
        "company": company,
        "location": loc_text or ("Remote" if work_type == "remote" else city),
        "city": city,
        "country": "US",
        "work_type": work_type,
        "distance_mi": distance,
        "salary_min": salary[0],
        "salary_max": salary[1],
        "salary_period": salary[2],
        "description": description,
        "url": url,
        "company_url": url,          # always the company's own posting
        "apply_options": None,
        "posted_at": posted,
        # Which of your target titles it matched (used to compare pay with similar jobs).
        "search_title": next((t for t, words in zip(config.TARGET_TITLES, target_words())
                              if words <= normalize_title(title)), "company board"),
    }


# Proper company names for board keys that don't capitalize nicely.
DISPLAY_NAMES = {
    "doordashusa": "DoorDash", "hubspotjobs": "HubSpot", "openai": "OpenAI", "scaleai": "Scale AI",
    "gitlab": "GitLab", "mongodb": "MongoDB", "elevenlabs": "ElevenLabs", "posthog": "PostHog",
}


def _company(key):
    return DISPLAY_NAMES.get(key, key.title())


def _text(html_text):
    """Turn a job description's HTML into plain text."""
    t = html.unescape(html.unescape(html_text or ""))
    t = re.sub(r"<\s*(br|/p|/li|/h\d|/div)\s*/?>", "\n", t, flags=re.IGNORECASE)
    t = re.sub(r"<\s*li[^>]*>", "• ", t, flags=re.IGNORECASE)
    t = re.sub(r"<[^>]+>", "", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


# ---------------------------------------------------------------------------
# One converter per board type
# ---------------------------------------------------------------------------

def _from_greenhouse(raw, key):
    title = raw.get("title") or ""
    if not _wanted_title(title):
        return None
    loc = (raw.get("location") or {}).get("name", "")
    place = _place(loc)
    if not place:
        return None
    job = _job(key, raw.get("id"), title, _company(key), loc, place, "", raw.get("absolute_url"),
               posted=raw.get("updated_at"))
    job["_greenhouse"] = (key, raw.get("id"))
    return job


def _add_greenhouse_details(job):
    """Fetch the description and pay range for one Greenhouse job."""
    key_id = job.pop("_greenhouse", None)
    if not key_id:
        return job
    try:
        d = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{key_id[0]}/jobs/{key_id[1]}"
                         "?pay_transparency=true", timeout=30).json()
        job["description"] = _text(d.get("content"))
        pay = (d.get("pay_input_ranges") or [{}])[0]
        if pay.get("min_cents"):
            job["salary_min"] = pay["min_cents"] / 100
            job["salary_max"] = (pay.get("max_cents") or pay["min_cents"]) / 100
            job["salary_period"] = "YEAR"
        if job["work_type"] == "on-site":
            wt = location.detect_work_type(job["title"], job["description"])
            job["work_type"] = "hybrid" if wt == "hybrid" else "on-site"
    except Exception:
        pass
    return job


def _from_lever(raw, key):
    title = raw.get("text") or ""
    if not _wanted_title(title):
        return None
    cats = raw.get("categories") or {}
    loc = cats.get("location") or ", ".join(cats.get("allLocations") or [])
    place = _place(loc, workplace=raw.get("workplaceType") or "")
    if not place:
        return None
    description = raw.get("descriptionPlain") or ""
    for section in raw.get("lists") or []:
        description += f"\n\n{section.get('text', '')}:\n" + _text(section.get("content"))
    description += "\n\n" + (raw.get("additionalPlain") or "")
    s = raw.get("salaryRange") or {}
    period = {"per-year-salary": "YEAR", "per-hour-wage": "HOUR", "per-month-salary": "MONTH"}
    salary = (s.get("min"), s.get("max"), period.get(s.get("interval"))) if s else (None, None, None)
    return _job(key, raw.get("id"), title, _company(key), loc, place, description.strip(),
                raw.get("hostedUrl"), salary, posted=raw.get("createdAt"))


def _from_ashby(raw, key):
    title = raw.get("title") or ""
    if not _wanted_title(title) or not raw.get("isListed", True):
        return None
    loc = raw.get("location") or ""
    place = _place(loc, remote_flag=raw.get("isRemote") and raw.get("workplaceType") != "Hybrid",
                   workplace=raw.get("workplaceType") or "")
    if not place:
        return None
    salary = (None, None, None)
    for tier in ((raw.get("compensation") or {}).get("summaryComponents") or []):
        if tier.get("compensationType") == "Salary":
            interval = (tier.get("interval") or "").upper()
            salary = (tier.get("minValue"), tier.get("maxValue"),
                      "YEAR" if "YEAR" in interval else "HOUR" if "HOUR" in interval else None)
            break
    return _job(key, raw.get("id"), title, _company(key), loc, place,
                raw.get("descriptionPlain") or _text(raw.get("descriptionHtml")),
                raw.get("jobUrl"), salary, posted=raw.get("publishedAt"))
