"""
The setup / settings screen in the app. It's shown automatically the first
time the app opens, and any time after from "Settings" in the sidebar.

It saves your location, distances, job titles and extra background to
my_settings.json, your resumes to the resume/ folder, and your API keys to
keys/.env. All three stay on your computer.
"""

import importlib

import streamlit as st
from dotenv import dotenv_values

import config
import geocode
import resume_reader

KEY_NAMES = ["JSEARCH_API_KEY", "USAJOBS_API_KEY", "USAJOBS_EMAIL"]


def save_keys(values):
    config.KEYS_FILE.parent.mkdir(exist_ok=True)
    lines = ["# Your API keys. This file stays on your computer (it's excluded from Git)."]
    lines += [f"{name}={values.get(name, '').strip()}" for name in KEY_NAMES]
    config.KEYS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def show():
    first_time = not config.IS_SET_UP
    s = config.load_settings()
    keys = dotenv_values(config.KEYS_FILE) if config.KEYS_FILE.exists() else {}

    st.header("👋 Welcome! Let's set up your job search" if first_time else "⚙️ Settings")
    if first_time:
        st.write("Fill this in once. You can change any of it later from **Settings** in the sidebar. "
                 "Everything you enter stays on your computer.")

    # --- Resumes (outside the form so uploads save right away) ---
    st.subheader("1. Your resume")
    st.caption("A .docx, .pdf or .txt file. Got more than one (say, one for data analyst roles and one "
               "for ML roles)? Add them all: each job is scored against every resume and tells you "
               "which one to send.")
    uploads = st.file_uploader("Add resume files", type=["docx", "pdf", "txt"], accept_multiple_files=True)
    for f in uploads or []:
        config.RESUME_DIR.mkdir(exist_ok=True)
        (config.RESUME_DIR / f.name).write_bytes(f.getbuffer())
    existing = resume_reader.load_resumes()
    if existing:
        st.success("Resumes found: " + ", ".join(f"**{label}**" for label in existing))
    else:
        st.warning("No resume yet. Add at least one so jobs can be scored.")

    with st.form("settings"):
        st.subheader("2. Where you are")
        city = st.text_input("Your city and state", value=s["home_city"], placeholder="e.g. Austin, TX")
        c1, c2 = st.columns(2)
        hybrid = c1.number_input("Hybrid jobs: how many miles away is OK?", 5, 300,
                                 int(s["hybrid_max_miles"]), step=5)
        onsite = c2.number_input("On-site (5 days a week): how many miles?", 5, 300,
                                 int(s["onsite_max_miles"]), step=5)
        st.caption("Remote jobs are always included, from anywhere in the US. "
                   "Distances are straight-line miles, not drive time.")

        st.subheader("3. Job titles to search for")
        titles = st.text_area("One per line", value="\n".join(s["target_titles"]), height=180,
                              help="Each title is one search. With JSearch, each title uses 2 of your "
                                   "200 free monthly requests per refresh.")

        st.subheader("4. Anything not on your resume? (optional)")
        extra = st.text_area("Leadership, side projects or experience you want counted", value=s["extra_background"],
                             placeholder="e.g. Captain of my college soccer team; ran a small tutoring business")

        st.subheader("5. Free API keys (optional)")
        st.caption("Without keys you still get jobs from about 50 tech company career pages. Keys add "
                   "Indeed, LinkedIn, Glassdoor and more (JSearch) and federal jobs (USAJobs).")
        jsearch = st.text_input("JSearch key", value=keys.get("JSEARCH_API_KEY") or "", type="password",
                                help="Free 'Basic' plan at rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch, "
                                     "then copy your X-RapidAPI-Key.")
        k1, k2 = st.columns(2)
        usa_key = k1.text_input("USAJobs key", value=keys.get("USAJOBS_API_KEY") or "", type="password",
                                help="Request one free at developer.usajobs.gov/apirequest")
        usa_email = k2.text_input("Email you used for USAJobs", value=keys.get("USAJOBS_EMAIL") or "")

        saved = st.form_submit_button("Save and start" if first_time else "Save settings", type="primary")

    if saved:
        title_list = [t.strip() for t in titles.splitlines() if t.strip()]
        spot = geocode.lookup(city) if city.strip() else None
        if not spot:
            st.error(f"Couldn't find \"{city}\" on the map. Try \"City, ST\", e.g. \"Austin, TX\".")
            return
        if not title_list:
            st.error("Add at least one job title.")
            return
        config.save_settings({
            "home_city": city.strip(), "home_lat": spot["lat"], "home_lon": spot["lon"],
            "hybrid_max_miles": int(hybrid), "onsite_max_miles": int(onsite),
            "target_titles": title_list, "extra_background": extra.strip(),
        })
        save_keys({"JSEARCH_API_KEY": jsearch, "USAJOBS_API_KEY": usa_key, "USAJOBS_EMAIL": usa_email})
        importlib.reload(config)  # use the new settings straight away
        st.session_state["show_settings"] = False
        st.session_state["just_set_up"] = first_time
        st.rerun()

    if not first_time and st.button("← Back to my jobs"):
        st.session_state["show_settings"] = False
        st.rerun()
