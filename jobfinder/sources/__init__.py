"""
Job sources. Each source is a module with a `fetch(title, conn)` function
that returns a list of jobs in the same standard format (see jsearch.py).
A source can instead have `fetch_everything(conn)`, which is called once per
refresh (see company_boards.py).

To add a new source later: write a new module with one of those functions,
then add it to the SOURCES list below.
"""

from . import company_boards, jsearch, usajobs

SOURCES = [company_boards, jsearch, usajobs]
