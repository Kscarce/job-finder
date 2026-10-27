"""
STEP 2: Scores every saved job against your resumes.

Three scores per job:
  fit_score   (0-100) how well the job matches you
  pay_score   (0-100) how its salary compares to other jobs with the same title
  apply_score (0-100) the Apply First rank: mostly fit, some pay

How the fit score works:
  1. A free AI model (all-MiniLM-L6-v2) turns text into "meaning vectors", so
     "built a classifier" and "develop ML models" count as similar even though
     they share no words. Each job is compared to each full resume, and to
     each piece of your background (skills, degree and coursework,
     dissertation, leadership).
  2. Simple rules based on your profile adjust that score (target title,
     entry-level, key skills, years of experience, PhD, clearance, seniority).
  3. TF-IDF (plain word matching) is used as a small tie-breaker, and as a
     backup if the AI model can't load.
"""

import os
import re
import warnings

import numpy as np

import config
import resume_reader

# ---------------------------------------------------------------------------
# Rules: points added to or taken from the fit score
# ---------------------------------------------------------------------------

KEY_SKILLS = {               # skill name shown in the reason: pattern to look for
    "Python": r"\bpython\b",
    "SQL": r"\bsql\b",
    "machine learning": r"machine learning|\bml\b",
    "statistics": r"statistic",
}
POINTS_PER_SKILL = 2         # up to 4 skills -> up to +8

ENTRY_LEVEL = r"entry[- ]level|new grad|recent grad|early career|junior|\bjr\.?\b|associate|level i\b|\bi\b$|0-2 years|0 to 2 years"
SENIOR = r"\bsenior\b|\bsr\.?\b|\blead\b|principal|\bstaff\b|manager|director|\bhead of\b|architect|\biii\b|\biv\b"
MID_LEVEL = r"mid[- ]?level|\bii\b|\bexperienced\b"
INTERN = r"\bintern(ship)?\b"
CLEARANCE = r"ts/sci|top secret|secret clearance|active secret|security clearance|clearance required|polygraph"
PHD = r"\bph\.?d\b|doctorate|doctoral"
MASTERS = r"master'?s|\bm\.?s\.?\b|\bmsc\b|graduate degree"

# Listings shorter than this are usually just a summary of the real posting,
# so the experience they ask for can't be checked.
SHORT_LISTING_CHARS = 1000

# Numbers written as digits or words: "5", "five", "five (5)".
WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
                "seven": 7, "eight": 8, "nine": 9, "ten": 10}
NUM = r"(\d{1,2}|" + "|".join(WORD_NUMBERS) + r")(?:\s*\(\d{1,2}\))?"
YEARS_WORD = r"\s*\+?\s*(?:(?:-|–|to)\s*\d{1,2}\s*\+?\s*)?(?:years?|yrs?)\b"

YEARS_PATTERNS = [
    # "3+ years of experience", "5-7 yrs relevant experience", "five (5) years of professional experience"
    re.compile(NUM + YEARS_WORD + r"(?:\s+of)?(?:\s+[\w/-]+){0,4}?\s+(?:experience|exp\b)", re.IGNORECASE),
    # "experience: 4+ years", "experience of at least 3 years"
    re.compile(r"experience[^.\n]{0,40}?" + NUM + YEARS_WORD, re.IGNORECASE),
    # "minimum of 5 years", "at least four years"
    re.compile(r"(?:minimum|at least)(?:\s+of)?\s+" + NUM + YEARS_WORD, re.IGNORECASE),
    # "4+ years building and shipping software", "3 years working in analytics", "2+ years in a SOC"
    re.compile(NUM + YEARS_WORD + r"\s+(?:of\s+)?(?:[a-z]+ing|in|as|hands-on|professional|industry)\b",
               re.IGNORECASE),
]

# Fit can't go above these, however well the skills match: a job that needs far
# more experience than you have shouldn't look like a strong fit.
FIT_CAP_SENIOR = 45          # senior/lead/manager title, or 5+ years asked for
FIT_CAP_3_TO_4_YEARS = 60    # 3-4 years asked for

# A starting salary this high almost always means an experienced hire, even
# when the posting doesn't say how many years it wants.
SENIOR_PAY_FLOOR = 200_000   # per year
FIT_CAP_SENIOR_PAY = 55


def years_required(text):
    """The most years of experience the posting asks for (ignoring silly numbers), or None."""
    found = []
    for pattern in YEARS_PATTERNS:
        for n in pattern.findall(text):
            n = WORD_NUMBERS.get(n.lower()) if not n.isdigit() else int(n)
            if n and 0 < n <= 15:
                found.append(n)
    return max(found) if found else None


# Shorthand in job titles, expanded so "ML Engineer" matches "Machine Learning Engineer".
TITLE_SHORTHAND = {
    r"\bml\b": "machine learning",
    r"\bai\b": "artificial intelligence",
    r"\bbi\b": "business intelligence",
    r"cyber\s*security": "cyber security",
    r"\binfosec\b": "information security",
    r"\bsoc\b": "security operations",
}


def normalize_title(title):
    """Lowercase, drop (notes) and [tags], expand shorthand, keep only words."""
    t = re.sub(r"\(.*?\)|\[.*?\]", " ", title.lower())
    for pattern, full in TITLE_SHORTHAND.items():
        t = re.sub(pattern, full, t)
    return set(re.findall(r"[a-z]+", t))


TARGET_WORDS = [normalize_title(t) for t in config.TARGET_TITLES]


def title_matches_target(title):
    """True if the title contains every word of one of your target titles."""
    words = normalize_title(title)
    return any(target <= words for target in TARGET_WORDS)


def apply_rules(title, description, min_yearly_pay=None):
    """
    Returns (points, cap, skills, positives, negatives). `cap` is the highest
    fit score allowed (100 = no cap). Positives and negatives are short
    phrases used to build the plain-language reason.
    """
    t, d = title.lower(), description.lower()
    points, cap, positives, negatives = 0, 100, [], []

    if title_matches_target(title):
        points += 8
        positives.append("title matches your targets")

    # Entry-level / new-grad roles.
    if re.search(SENIOR, t):
        points -= 15
        cap = FIT_CAP_SENIOR
        negatives.append("senior-level title")
    elif re.search(MID_LEVEL, t):
        points -= 8
        negatives.append("mid-level title")
    elif re.search(INTERN, t):
        points -= 10
        negatives.append("internship, not full-time")
    elif re.search(ENTRY_LEVEL, t) or re.search(r"entry[- ]level|new grad|recent graduate", d):
        points += 8
        positives.append("entry-level")

    # Key skills.
    skills = [name for name, pattern in KEY_SKILLS.items() if re.search(pattern, d)]
    points += POINTS_PER_SKILL * len(skills)

    # Years of experience.
    years = years_required(description)
    if years is not None:
        if years >= 5:
            points -= 20
            cap = min(cap, FIT_CAP_SENIOR)
        elif years >= 3:
            points -= 10
            cap = min(cap, FIT_CAP_3_TO_4_YEARS)
        elif years == 2:
            points -= 4
        if years >= 2:
            negatives.append(f"asks for {years}+ years of experience")
    elif min_yearly_pay and min_yearly_pay >= SENIOR_PAY_FLOOR:
        points -= 10
        cap = min(cap, FIT_CAP_SENIOR_PAY)
        negatives.append(f"starting pay over ${SENIOR_PAY_FLOOR // 1000}k suggests a senior role")
    elif len(description) < SHORT_LISTING_CHARS:
        # Only a short summary: we can't see what experience the real posting asks for.
        points -= 10
        negatives.append("short listing, so check the experience required on the posting")

    # A degree you don't have: a PhD with no master's alternative.
    if re.search(PHD, d) and not re.search(MASTERS, d):
        points -= 15
        negatives.append("asks for a PhD")

    # Security clearance (you'd need to already have one for most of these).
    if re.search(CLEARANCE, t + " " + d):
        points -= 15
        negatives.append("requires a security clearance")

    return points, cap, skills, positives, negatives


# ---------------------------------------------------------------------------
# The AI model
# ---------------------------------------------------------------------------

_model = None


def load_model():
    """Loads the embedding model once. Returns None if it can't (TF-IDF is used instead)."""
    global _model
    if _model is None:
        # Hide harmless Hugging Face warnings (no login, Windows file shortcuts).
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        warnings.filterwarnings("ignore", module="huggingface_hub")
        try:
            from huggingface_hub.utils import logging as hf_logging
            hf_logging.set_verbosity_error()
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(config.EMBEDDING_MODEL)
        except Exception as e:
            print(f"WARNING: couldn't load the AI model ({e}). Using word matching only.")
            _model = False
    return _model or None


def chunks(text, words=150):
    """
    The model only reads about 250 words at a time, so long text is split into
    overlapping chunks of ~150 words. Otherwise most of a job description
    would be ignored.
    """
    w = text.split()
    if len(w) <= words:
        return [text]
    step = words - 30
    return [" ".join(w[i:i + words]) for i in range(0, len(w) - 30, step)]


def embed(model, texts):
    """Meaning vectors, normalized so a dot product = cosine similarity."""
    return model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False)


def embed_document(model, text):
    """One vector for a whole document: the average of its chunk vectors."""
    v = embed(model, chunks(text)).mean(axis=0)
    return v / np.linalg.norm(v)


def similarity_to_points(sim):
    """
    Converts raw model similarity to 0-100. Measured on real listings, job vs
    resume similarity runs from about 0.25 (unrelated, e.g. a radiologist job)
    to about 0.58 (closest match), with the typical job around 0.41.
    """
    return float(np.clip((sim - 0.25) / (0.60 - 0.25), 0, 1) * 100)


def strength_word(semantic):
    if semantic >= 70:
        return "Strong match"
    if semantic >= 50:
        return "Good match"
    if semantic >= 30:
        return "Some match"
    return "Weak match"


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_jobs(jobs):
    """
    jobs: list of dicts with at least id, title, description, search_title,
    salary_min, salary_max, salary_period.
    Returns {job id: {fit_score, fit_reason, best_resume, pay_score, apply_score}}.
    """
    resumes = resume_reader.load_resumes()
    if not resumes:
        raise SystemExit(f"No resume found. Put a .docx, .pdf or .txt file in {config.RESUME_DIR}")

    pieces = resume_reader.background_pieces(resumes)
    for name, extra in config.EXTRA_BACKGROUND.items():
        pieces[name] = (pieces.get(name, "") + "\n" + extra).strip()

    model = load_model()
    tfidf = tfidf_scores(jobs, resumes)

    if model:
        resume_vecs = {label: embed_document(model, text) for label, text in resumes.items()}
        piece_vecs = {name: embed_document(model, text) for name, text in pieces.items()}

    results = {}
    for job in jobs:
        title, description = job["title"] or "", job["description"] or ""
        full_text = f"{title}\n{description}"

        if model:
            job_chunks = embed(model, chunks(full_text))
            job_vec = job_chunks.mean(axis=0)
            job_vec /= np.linalg.norm(job_vec)

            # Whole job vs each whole resume. The best one wins.
            by_resume = {label: float(job_vec @ v) for label, v in resume_vecs.items()}
            best_resume = max(by_resume, key=by_resume.get)

            # Each piece of your background vs the best-matching part of the job.
            piece_sim = sum(
                config.PIECE_WEIGHTS[name] * float((job_chunks @ v).max())
                for name, v in piece_vecs.items()
            )
            semantic = similarity_to_points(0.5 * by_resume[best_resume] + 0.5 * piece_sim)
        else:
            # Backup: word matching only.
            by_resume = tfidf[job["id"]]
            best_resume = max(by_resume, key=by_resume.get)
            semantic = float(np.clip(by_resume[best_resume] / 0.35, 0, 1) * 100)

        lowest_pay = (job["salary_min"] or 0) * PER_YEAR.get((job["salary_period"] or "YEAR").upper(), 1)
        points, cap, skills, positives, negatives = apply_rules(title, description, lowest_pay)
        tiebreak = 3 * max(tfidf[job["id"]].values())  # word overlap, worth at most ~1-2 points
        fit = float(np.clip(semantic + points + tiebreak, 0, cap))

        results[job["id"]] = {
            "fit_score": round(fit),
            "fit_reason": build_reason(semantic, skills, positives, negatives),
            "best_resume": best_resume,
        }

    add_pay_scores(jobs, results)
    return results


def build_reason(semantic, skills, positives, negatives):
    """e.g. "Strong match on Python and machine learning, entry-level, but asks for 3+ years of experience" """
    reason = strength_word(semantic)
    if skills:
        reason += " on " + (" and ".join(skills) if len(skills) <= 2
                            else ", ".join(skills[:-1]) + " and " + skills[-1])
    if positives:
        reason += ", " + ", ".join(positives)
    if negatives:
        reason += ", but " + " and ".join(negatives)
    return reason


def tfidf_scores(jobs, resumes):
    """Plain word-overlap similarity of each job to each resume: {job id: {resume label: 0-1}}."""
    from sklearn.feature_extraction.text import TfidfVectorizer

    labels = list(resumes)
    docs = [resumes[l] for l in labels] + [f"{j['title']}\n{j['description'] or ''}" for j in jobs]
    matrix = TfidfVectorizer(stop_words="english", sublinear_tf=True).fit_transform(docs)
    sims = (matrix[len(labels):] @ matrix[:len(labels)].T).toarray()
    return {job["id"]: dict(zip(labels, map(float, row))) for job, row in zip(jobs, sims)}


# ---------------------------------------------------------------------------
# Pay
# ---------------------------------------------------------------------------

PER_YEAR = {"YEAR": 1, "HOUR": 2080, "MONTH": 12, "WEEK": 52, "BIWEEKLY": 26}


def yearly_pay(job):
    """Midpoint of the salary range, converted to a yearly amount. None if not listed."""
    lo, hi = job["salary_min"], job["salary_max"]
    if not lo and not hi:
        return None
    mid = ((lo or hi) + (hi or lo)) / 2
    return mid * PER_YEAR.get((job["salary_period"] or "YEAR").upper(), 1)


def add_pay_scores(jobs, results):
    """
    Pay score compares the job's pay to the typical (median) pay of jobs found
    for the same title: 50 = typical, 100 = 50% or more above it, 0 = 50% or
    more below it. If fewer than 3 jobs for that title list pay, it's compared
    to all jobs instead.
    Apply First = fit x 0.75 + pay x 0.25, with unlisted pay counted as typical (50).
    """
    pay = {j["id"]: yearly_pay(j) for j in jobs}
    all_pays = [p for p in pay.values() if p]

    for job in jobs:
        r = results[job["id"]]
        p = pay[job["id"]]
        if p:
            group = [pay[j["id"]] for j in jobs if j["search_title"] == job["search_title"] and pay[j["id"]]]
            if len(group) < 3:
                group = all_pays
            typical = float(np.median(group))
            r["pay_score"] = round(float(np.clip(50 + 100 * (p - typical) / typical, 0, 100)))
        else:
            r["pay_score"] = None

        pay_part = r["pay_score"] if r["pay_score"] is not None else 50
        r["apply_score"] = round(config.FIT_WEIGHT * r["fit_score"] + (1 - config.FIT_WEIGHT) * pay_part)
