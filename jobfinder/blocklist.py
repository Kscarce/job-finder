"""
Throws out jobs from spam sites, scammy companies, and gig work you don't
want. The lists themselves live in config.py so they're easy to edit.
"""

import re
from urllib.parse import urlparse

import config

# A dollar amount quoted per hour: "$45/hr", "$25.00 - $40.00 per hour", "$30 an hour".
# Only 2-3 digit amounts, so salary boilerplate like "$66,330 ... base hourly rate
# or annual salary" doesn't count.
HOURLY_RATE = re.compile(
    r"\$\s?\d{2,3}(?:\.\d{2})?\s*(?:(?:-|–|to)\s*\$?\s?\d{2,3}(?:\.\d{2})?\s*)?"
    r"(?:/\s?h(?:ou)?r\b|per hour|an hour|hourly)",
    re.IGNORECASE,
)


# Pay-to-train "placement programs" posing as jobs.
# Any one strong sign is enough; soft signs need two, since a real employer
# might mention one of them (e.g. "upskilling" as a benefit).
PLACEMENT_STRONG = re.compile(
    r"training (?:and|&) placement|job placement program|placement (?:assistance|guarantee)|"
    r"guaranteed (?:job|placement|interviews)|(?:training|program|placement) fees?\b|"
    r"upfront (?:fee|payment|cost)|pay for (?:the |our )?training",
    re.IGNORECASE,
)
PLACEMENT_SOFT = [
    r"marketing team|market(?:ing)? your (?:profile|resume)",
    r"(?:after|upon) (?:the )?successful completion",
    r"struggling to land interviews|ghosted after applying|tired of (?:being )?ghosted",
    r"upskill|skill enhancement|clos(?:e|ing) the (?:skills? )?gap between",
    r"career gaps|career switch to tech|lacking real-world experience",
]


def is_placement_program(job):
    text = job.get("description") or ""
    if PLACEMENT_STRONG.search(text):
        return True
    return sum(bool(re.search(p, text, re.IGNORECASE)) for p in PLACEMENT_SOFT) >= 2


def is_hourly(job):
    if (job.get("salary_period") or "").upper() == "HOUR":
        return True
    return bool(HOURLY_RATE.search(f"{job.get('title') or ''} {job.get('description') or ''}"))


def blocked_reason(job):
    """Returns why a job is blocked (e.g. "site: dedyn.io"), or None if it's fine."""
    site = urlparse(job.get("url") or "").hostname or ""
    for blocked in config.BLOCKED_SITES:
        # Match the site itself and any sub-site, e.g. "us.remotejobs.dedyn.io".
        if site == blocked or site.endswith("." + blocked):
            return f"site: {blocked}"

    company = (job.get("company") or "").lower()
    for blocked in config.BLOCKED_COMPANIES:
        if blocked in company:
            return f"company: {blocked}"

    title = (job.get("title") or "").lower()
    for word in config.BLOCKED_TITLE_WORDS:
        if word in title:
            return f"title: {word}"

    if config.EXCLUDE_PLACEMENT_PROGRAMS and is_placement_program(job):
        return "training/placement program"

    if config.EXCLUDE_HOURLY_PAY and is_hourly(job):
        return "hourly pay"

    return None
