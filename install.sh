#!/bin/bash
# Run once to install Job Finder on Mac or Linux:   bash install.sh
# It sets up a private copy of Python's packages in this folder (.venv).
cd "$(dirname "$0")"
echo "Installing Job Finder. This takes about 5-10 minutes the first time."

# Find Python 3.11, 3.12 or 3.13 (PyTorch doesn't support newer versions yet).
PY=""
for v in 3.13 3.12 3.11; do
    if command -v "python$v" >/dev/null 2>&1; then PY="python$v"; break; fi
done
if [ -z "$PY" ] && command -v python3 >/dev/null 2>&1; then
    if python3 -c 'import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] <= (3, 13) else 1)'; then PY="python3"; fi
fi
if [ -z "$PY" ]; then
    echo
    echo "Couldn't find Python 3.11-3.13."
    echo "Install Python 3.13 from https://www.python.org/downloads/ (or: brew install python@3.13),"
    echo "then run this again."
    exit 1
fi
echo "Using $PY"

[ -d .venv ] || "$PY" -m venv .venv || exit 1
.venv/bin/python -m pip install --upgrade pip --quiet
.venv/bin/python -m pip install -r requirements.txt || { echo "Install failed. Check your internet connection and try again."; exit 1; }

chmod +x open-app.sh
echo
echo "Done! Start Job Finder with:   ./open-app.sh"
