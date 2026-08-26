"""
conftest.py - the shared setup every test file can rely on.

pytest loads this file automatically before the tests, so anything defined
here is available to all of them without being imported. It does two jobs:
it puts the project's own modules on the import path, and it provides the
few small helpers the tests keep needing.
"""

import sys
from pathlib import Path

# The tests live in a folder of their own, so Python has to be told where
# the project's modules are. Everything is resolved from THIS file's
# location rather than from the working directory, so "pytest" works the
# same whether it is run from the project folder or from anywhere else.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

SAMPLES = PROJECT_ROOT / "Sample Documents"
WORD_SAMPLES = SAMPLES / "Word"
LATEX_SAMPLES = SAMPLES / "LaTeX"
ODT_SAMPLES = SAMPLES / "LibreOffice"


# The sample documents are checked with no section requirements, so the
# ladder tests measure the STYLE checks only. The section checks get their
# own tests, with their own explicit list. Spelling this out here means the
# tests do not quietly change meaning if the built-in defaults are edited.
NO_SECTIONS = {"sections": []}


def issue_counts(model, structure=NO_SECTIONS, styles=None):
    """
    Run the checks and return {check id: how many times it fired}.

    Comparing these small dictionaries is how the ladder tests state their
    expectations: it says exactly which checks reacted and how often,
    without depending on the wording of any message.
    """
    from rules import run_checks

    counts = {}
    for issue in run_checks(model, structure, styles):
        counts[issue.check] = counts.get(issue.check, 0) + 1
    return counts


def checks_fired(model, structure=NO_SECTIONS, styles=None):
    """The set of check ids that reported something. Order does not matter."""
    return set(issue_counts(model, structure, styles))
