"""
Works out how far a job is from home, whether it's remote / hybrid / on-site,
and whether it passes your location rules.
"""

import math
import re

import config


def miles_from_home(lat, lon):
    """Straight-line distance in miles from home (not drive time). None if no coordinates."""
    if lat is None or lon is None:
        return None
    # Haversine formula: distance between two points on a sphere.
    r = 3958.8  # Earth's radius in miles
    p1, p2 = math.radians(config.HOME_LAT), math.radians(lat)
    dp = math.radians(lat - config.HOME_LAT)
    dl = math.radians(lon - config.HOME_LON)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(a)), 1)


# Phrases that clearly mean the whole job is remote. A plain "remote" in a long
# description is too loose (e.g. "remote sensing", "no remote work"), so we
# only trust these in the description; "remote" in the title is enough.
REMOTE_PHRASES = re.compile(
    r"fully remote|100% remote|remote position|remote role|remote opportunity|"
    r"work from home|work-from-home|\bwfh\b|remote-first|remote \(us\)|remote, us",
    re.IGNORECASE,
)


def detect_work_type(title, description, api_says_remote=False, api_says_hybrid=False):
    """
    Use the API's label when there is one. Otherwise look for keywords in
    the title and description. Returns "remote", "hybrid", or "on-site".
    """
    title = title or ""
    description = description or ""

    if api_says_hybrid or "hybrid" in title.lower():
        return "hybrid"
    if api_says_remote or "remote" in title.lower():
        return "remote"
    if "hybrid" in description.lower():
        return "hybrid"
    if REMOTE_PHRASES.search(description):
        return "remote"
    return "on-site"


def passes_location_rules(work_type, distance_mi, country="US"):
    """
    Your rules:
      remote  -> anywhere in the US
      hybrid  -> within 75 miles
      on-site -> within 40 miles
    Hybrid/on-site jobs with an unknown distance (only a state listed) follow
    the KEEP_UNKNOWN_DISTANCE setting in config.py.
    """
    if country and country.upper() not in ("US", "USA", "UNITED STATES"):
        return False
    if work_type == "remote":
        return True
    if distance_mi is None:
        return config.KEEP_UNKNOWN_DISTANCE
    if work_type == "hybrid":
        return distance_mi <= config.HYBRID_MAX_MILES
    return distance_mi <= config.ONSITE_MAX_MILES


def make_dedupe_key(title, company, city):
    """Same title + company + city = same job, even if two sources both list it."""
    def clean(s):
        return re.sub(r"[^a-z0-9]", "", (s or "").lower())
    return f"{clean(title)}|{clean(company)}|{clean(city)}"
