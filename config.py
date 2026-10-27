"""
All the settings you're likely to want to change live in this one file.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Where things are stored
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).parent
KEYS_FILE = PROJECT_DIR / "keys" / ".env"   # your API keys
DATA_DIR = PROJECT_DIR / "data"             # the SQLite database goes here
DB_FILE = DATA_DIR / "jobs.db"
RESUME_DIR = PROJECT_DIR / "resume"         # put your resume files here (.docx, .pdf or .txt)

# ---------------------------------------------------------------------------
# Your location
# ---------------------------------------------------------------------------
HOME_CITY = "Danville, VA"
HOME_CITY_LONG = "Danville, Virginia"       # USAJobs prefers the full state name
HOME_LAT = 36.5860
HOME_LON = -79.3950

# ---------------------------------------------------------------------------
# Which jobs to keep, by work type
#   remote  -> anywhere in the US
#   hybrid  -> within HYBRID_MAX_MILES of home
#   on-site -> within ONSITE_MAX_MILES of home (a daily commute)
# ---------------------------------------------------------------------------
HYBRID_MAX_MILES = 75
ONSITE_MAX_MILES = 40

# Some hybrid/on-site listings only give a state ("Virginia"), so we can't tell
# how far away they are. False = drop them. True = keep them, marked "distance unknown".
KEEP_UNKNOWN_DISTANCE = False

# The local search uses the wider of the two radii, then we filter by type.
SEARCH_RADIUS_MILES = max(HYBRID_MAX_MILES, ONSITE_MAX_MILES)

# ---------------------------------------------------------------------------
# Job titles to search for
# ---------------------------------------------------------------------------
TARGET_TITLES = [
    "Data Scientist",
    "Business Intelligence Analyst",
    "Technical Consultant",
    "AI Engineer",
    "Machine Learning Engineer",
    "Data Analyst",
    "BI Developer",
    "Applied Scientist",
    "Information Security Analyst",
    "Security Analyst",
]

# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

# Free sentence-embedding model from Hugging Face. Downloads once (~90 MB),
# then runs on your computer with no internet needed.
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Background that isn't on your resumes but should count. Added to the
# matching piece of your background when scoring.
EXTRA_BACKGROUND = {
    "leadership": "Ran my own volleyball lessons, coaching players one-on-one and in groups, "
                  "showing leadership and initiative.",
}

# How much each piece of your background counts toward the fit score (adds up to 1).
PIECE_WEIGHTS = {
    "skills": 0.35,
    "degree and coursework": 0.30,
    "dissertation": 0.20,
    "leadership": 0.15,
}

# Apply First rank = fit x FIT_WEIGHT + pay x (1 - FIT_WEIGHT).
# Jobs with no salary listed get an average pay score (50), so they aren't punished.
FIT_WEIGHT = 0.75

# ---------------------------------------------------------------------------
# Blocklist: jobs matching any of these are thrown away.
# Add to these lists whenever you spot junk. Matching ignores upper/lower case.
# ---------------------------------------------------------------------------

# Websites (the job link's address). Blocking "example.com" also blocks
# "jobs.example.com". These are free-hosting or spam sites, not real job boards.
BLOCKED_SITES = [
    "dedyn.io",            # "remote quest jobs" spam reposts
    "talk4fun.net",        # "WFHQuillen" fake work-from-home listings
    "liveblog365.com",     # free blog host posing as a job site
    "totalh.net",          # free web host posing as a job site
    "theelitejob.com",     # vague work-from-home listings
    "sumafinanciera.mx",   # financial site scraping job ads
    "upwork.com",          # freelance gigs, not full-time jobs
]

# Companies (the "company" name on the listing). A partial match is enough.
BLOCKED_COMPANIES = [
    "remote quest jobs",
    "wfhquillen",
    "the elite job",
    "remotejobsone",       # "Junior" roles at $150-200/hr: too good to be true
    "synergisticit",       # pay-to-train "placement program", not a real job
    # AI-training gig shops: hourly freelance work labeling data for AI models,
    # not full-time roles. Delete any line here if you want to see them.
    "ai training",
    "dataannotation",
    "mercor",
    "micro1",
    "alignerr",
    "synthires",
    "24-mag",
    "afterquery",
]

# Drop "training and placement" programs dressed up as jobs: you pay for or sign
# up to their training, and they market your resume to clients later.
# Spotted by wording in the description (see PLACEMENT_SIGNS in blocklist.py).
EXCLUDE_PLACEMENT_PROGRAMS = True

# Drop jobs that pay by the hour (an hourly salary, or an hourly rate like
# "$45/hr" in the title or description). Set to False to see them again.
EXCLUDE_HOURLY_PAY = True

# Words in the job title.
BLOCKED_TITLE_WORDS = [
    "data entry",          # common work-from-home scam
    "ai trainer",
    "ai training",
]

# ---------------------------------------------------------------------------
# Company job boards: free, unlimited, and every link goes to the company's
# own posting. Add a company by finding its careers page address:
#   job-boards.greenhouse.io/NAME  or boards.greenhouse.io/NAME -> "greenhouse"
#   jobs.lever.co/NAME                                       -> "lever"
#   jobs.ashbyhq.com/NAME                                    -> "ashby"
# Microsoft, Apple, Google, Amazon and Meta use their own systems with no
# free feed, so they aren't here (JSearch still finds some of their jobs).
# ---------------------------------------------------------------------------
COMPANY_BOARDS = {
    "greenhouse": [
        "affirm", "airbnb", "anthropic", "asana", "brex", "chime", "cloudflare",
        "coinbase", "databricks", "datadog", "discord", "doordashusa", "dropbox",
        "duolingo", "figma", "gitlab", "gusto", "hubspotjobs", "instacart", "lyft",
        "mongodb", "nextdoor", "nuro", "okta", "pinterest", "reddit", "robinhood",
        "roblox", "samsara", "scaleai", "squarespace", "stripe", "toast", "twilio",
        "twitch", "waymo",
    ],
    "lever": ["palantir", "spotify", "zoox"],
    "ashby": [
        "cohere", "deepgram", "elevenlabs", "linear", "notion", "openai", "perplexity",
        "posthog", "ramp", "replit", "supabase",
    ],
}

# Skip senior roles from company boards (they're mostly Senior/Staff/Principal).
BOARDS_SKIP_SENIOR = True

# Office cities near home, so hybrid/on-site board jobs get a distance.
# (Board listings give a city name but no map coordinates.)
NEARBY_CITIES = {
    "raleigh": (35.7796, -78.6382), "durham": (35.9940, -78.8986),
    "chapel hill": (35.9132, -79.0558), "research triangle": (35.8992, -78.8636),
    "morrisville": (35.8235, -78.8256), "cary": (35.7915, -78.7811),
    "greensboro": (36.0726, -79.7920), "winston-salem": (36.0999, -80.2442),
    "burlington": (36.0957, -79.4378), "roanoke": (37.2710, -79.9414),
    "lynchburg": (37.4138, -79.1422), "danville": (36.5860, -79.3950),
}

# ---------------------------------------------------------------------------
# JSearch request budget
# The free plan has a monthly request limit. Each refresh makes 2 requests
# per title (one local search, one remote search) = 20 requests.
# ---------------------------------------------------------------------------
JSEARCH_MONTHLY_LIMIT = 200   # used until JSearch tells us the real number
JSEARCH_RESERVE = 10          # always keep this many requests unused, as a safety margin

# Only fetch jobs posted recently. Options: "all", "today", "3days", "week", "month".
# "week" suits a weekly refresh. Use "month" for your very first run if you like.
JSEARCH_DATE_POSTED = "week"
