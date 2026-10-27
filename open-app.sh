#!/bin/bash
# Starts Job Finder on Mac or Linux and opens it in your browser.
# Keep this terminal window open while you use the app; press Ctrl+C to stop it.
cd "$(dirname "$0")"
echo "Starting Job Finder... your browser will open in a few seconds."
( sleep 4; (command -v open >/dev/null && open http://localhost:8501) || xdg-open http://localhost:8501 ) >/dev/null 2>&1 &
.venv/bin/python -m streamlit run app.py --server.port 8501
