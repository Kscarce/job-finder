"""
Turns a place name ("Austin, TX") into map coordinates, so distances work
anywhere in the US.

Uses OpenStreetMap's free Nominatim service. Its rules: at most one lookup
per second, and a name identifying the app. Every answer is saved in
data/geocache.json, so each place is only ever looked up once.
"""

import json
import threading
import time

import requests

import config

URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "job-finder (https://github.com/Kscarce/job-finder)"}
CACHE_FILE = config.DATA_DIR / "geocache.json"

_cache = None
_last_lookup = 0.0
_lock = threading.Lock()  # company boards are downloaded in parallel; look up one at a time


def _load_cache():
    global _cache
    if _cache is None:
        _cache = json.loads(CACHE_FILE.read_text(encoding="utf-8")) if CACHE_FILE.exists() else {}
    return _cache


def lookup(place):
    """
    Returns {"lat": .., "lon": .., "name": ..} for a US place, or None if it
    can't be found (or the lookup fails).
    """
    with _lock:
        return _lookup(place)


def _lookup(place):
    global _last_lookup
    key = " ".join((place or "").lower().split())
    if not key:
        return None
    cache = _load_cache()
    if key in cache:
        return cache[key]

    # Be polite: no more than one request per second.
    wait = 1.1 - (time.time() - _last_lookup)
    if wait > 0:
        time.sleep(wait)
    _last_lookup = time.time()
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=20,
                            params={"q": place, "format": "json", "limit": 1, "countrycodes": "us"})
        resp.raise_for_status()
        found = resp.json()
    except Exception:
        return None  # not cached, so it's tried again next time

    result = ({"lat": float(found[0]["lat"]), "lon": float(found[0]["lon"]),
               "name": found[0].get("display_name", place)} if found else None)
    cache[key] = result
    config.DATA_DIR.mkdir(exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    return result
