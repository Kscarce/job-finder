"""
Finds the company's own posting among the places a job is listed, so you
can apply on the company's website instead of a job board or aggregator.
"""

import json
import re
from urllib.parse import quote_plus, urlparse

# Hiring systems companies use for their own careers pages. A link to one of
# these is almost always the company's real posting.
COMPANY_HIRING_SITES = [
    "myworkdayjobs.com", "workday.com", "greenhouse.io", "lever.co", "icims.com",
    "smartrecruiters.com", "ashbyhq.com", "jobvite.com", "careers-page.com",
    "applytojob.com", "bamboohr.com", "recruitee.com", "taleo.net",
    "successfactors.com", "ultipro.com", "paylocity.com", "adp.com", "breezy.hr",
    "workable.com", "rippling.com", "dayforcehcm.com", "oraclecloud.com",
    "usajobs.gov",
]

# Words that don't help match a company name to a website.
COMPANY_FILLER = {"inc", "llc", "ltd", "corp", "corporation", "company", "co", "group",
                  "the", "and", "of", "holdings", "services", "solutions", "technologies"}


def company_words(name):
    return [w for w in re.findall(r"[a-z0-9]+", (name or "").lower())
            if w not in COMPANY_FILLER and len(w) > 2]


def is_company_link(option, company):
    """True if this apply option looks like the company's own site."""
    if option.get("is_direct"):
        return True
    link = option.get("apply_link") or ""
    host = (urlparse(link).hostname or "").lower()
    if any(host == s or host.endswith("." + s) for s in COMPANY_HIRING_SITES):
        return True
    words = company_words(company)
    if not words:
        return False
    # The publisher is the company itself ("Enviroairsolutions"), or the site
    # is named after it ("careers.labcorp.com").
    publisher = " ".join(company_words(option.get("publisher")))
    host_text = host.replace("-", "")
    return publisher == " ".join(words) or any(w in host_text for w in words)


def pick_company_link(apply_options, company):
    """The company's own posting from JSearch's list of apply options, or None."""
    for option in apply_options or []:
        if is_company_link(option, company):
            return option.get("apply_link")
    return None


def options_json(apply_options):
    """The other places the job is posted, kept small for the database."""
    return json.dumps([{"publisher": o.get("publisher"), "apply_link": o.get("apply_link")}
                       for o in apply_options or [] if o.get("apply_link")])


def search_url(job):
    """A Google search for the job on the company's own site. Free, works for any job."""
    q = f'"{job.get("title") or ""}" {job.get("company") or ""} careers apply'
    return "https://www.google.com/search?q=" + quote_plus(q)
