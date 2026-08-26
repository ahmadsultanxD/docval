"""
app.py - the online user study for docval's Word checks.

A participant downloads a document with known structural faults, fixes it
in Word, and uploads their result here. The app runs the same checks the
command-line tool uses, shows the participant their own report, then asks
the UEQ-S (User Experience Questionnaire, Short Version) about the
experience. The report and the answers are logged together as one readable
row in a Google Sheet, so each row is one participant's complete
submission, with a proper header naming every column and the UEQ-S already
scored - not just the eight raw numbers.

This file only arranges the study around the engine; it does not judge
anything itself. Reading a document and deciding what is wrong with it is
still entirely word_extractor.py and rules.py, the same code the
command-line tool uses.
"""

import datetime
import sys
import uuid
from pathlib import Path

import streamlit as st

# The checking engine lives one level up, in the main docval project. This
# mirrors how tests/conftest.py finds it: resolved from this file's own
# location, not from wherever the app happens to be launched from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rules import run_checks                   # noqa: E402
from word_extractor import extract             # noqa: E402

TEMPLATE_PATH = PROJECT_ROOT / "Sample Documents" / "Word" / "Assignment_v5.docx"
# Offered to participants under a neutral name - "v1" would give away that
# it is the first, most-faulty rung of a labeled ladder.
TEMPLATE_DOWNLOAD_NAME = "assignment_template.docx"

# One friendly, spelled-out name per check id, written by hand rather than
# derived from the id, so the Google Sheet reads like a report and not like
# code. This is the ONE place the wording lives; the id itself never
# appears in the sheet.
CHECK_LABELS = {
    "heading-hierarchy": "Heading structure",
    "heading-numbering": "Heading numbering",
    "toc-present":       "Table of contents present",
    "toc-linked":        "Table of contents linked",
    "required-sections": "Required sections",
    "section-order":     "Section order",
    "list-formatting":   "List formatting",
    "table-caption":     "Table captions",
    "figure-caption":    "Figure captions",
    "equation-format":   "Equation format",
    "inline-image":      "Inline images",
}

# The eight official UEQ-S item pairs, in the instrument's own order and
# wording (Schrepp, Hinderks & Thomaschewski, 2017; ueq-online.org). Each is
# answered on a 1-7 scale, 1 meaning "closer to the left word" and 7
# "closer to the right word". The first four items score Pragmatic Quality
# (can the tool be used effectively); the last four score Hedonic Quality
# (was using it a good experience) - that grouping is what "scale" records
# below, and it is what the two summary scores are computed from.
#
# The official instrument sometimes swaps which side the positive word is
# on, per item, to reduce the tendency to rate everything on the same side.
# This app always puts the positive word on the right instead, which is
# simpler to build and to answer, at the cost of that safeguard - worth
# knowing if you are writing this up formally.
UEQ_ITEMS = [
    ("obstructive", "supportive", "pragmatic"),
    ("complicated", "easy", "pragmatic"),
    ("inefficient", "efficient", "pragmatic"),
    ("confusing", "clear", "pragmatic"),
    ("boring", "exciting", "hedonic"),
    ("not interesting", "interesting", "hedonic"),
    ("conventional", "inventive", "hedonic"),
    ("usual", "leading edge", "hedonic"),
]


def header_row():
    """
    The Google Sheet's column names, in the order every row is written.

    Kept as one function so the header and the data rows can never drift
    apart: both are built by walking the same lists, in the same order.
    The eight raw UEQ-S answers are included as well as the two scores
    computed from them, so the sheet holds both the interpretable summary
    and the underlying data a formal analysis would need.
    """
    return (["Time", "Participant ID", "File name", "Result", "Total issues"]
            + [CHECK_LABELS[check_id] for check_id in CHECK_LABELS]
            + [f"{left.capitalize()} - {right.capitalize()}"
               for left, right, _ in UEQ_ITEMS]
            + ["Pragmatic Quality (1-7)", "Hedonic Quality (1-7)"])


def ueq_scores(answers):
    """
    The two UEQ-S scale scores, each the mean of its four items.

    'answers' is the eight 1-7 ratings in UEQ_ITEMS order. Because every
    item here has its positive word on the right (see UEQ_ITEMS above), a
    plain mean is the score directly - no item needs to be reversed first.
    """
    pragmatic = [a for a, (_, _, scale) in zip(answers, UEQ_ITEMS)
                if scale == "pragmatic"]
    hedonic = [a for a, (_, _, scale) in zip(answers, UEQ_ITEMS)
              if scale == "hedonic"]
    return round(sum(pragmatic) / len(pragmatic), 2), \
        round(sum(hedonic) / len(hedonic), 2)


def ensure_header(sheet):
    """
    Make sure row 1 of the sheet is the header, and only the header.

    Checked on every submission rather than assumed once: a sheet an
    instructor has been testing against by hand may already hold data with
    no header row at all, which is exactly what produced unreadable output
    before this. If row 1 is not already the expected header, the header is
    inserted above whatever is there, so every row from this point on is
    readable even if older rows above it are not.
    """
    expected = header_row()
    values = sheet.get_all_values()
    if not values or values[0] != expected:
        sheet.insert_row(expected, index=1)


def get_sheet():
    """
    The Google Sheet results are logged to.

    Reads a service account from Streamlit's secrets - never from a file
    committed to the repository - and the target sheet's URL alongside it.
    Both must be configured in .streamlit/secrets.toml locally, or in the
    app's Secrets panel once deployed. See README.md in this folder.
    """
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=scopes)
    client = gspread.authorize(credentials)
    sheet = client.open_by_url(st.secrets["sheet"]["url"]).sheet1
    ensure_header(sheet)
    return sheet


def check_document(uploaded_file):
    """Run the same engine the command-line tool uses, on the upload."""
    model = extract(uploaded_file)
    return run_checks(model)


def issue_counts(issues):
    """{check id: how many times it fired}, including checks that did not."""
    counts = {check_id: 0 for check_id in CHECK_LABELS}
    for issue in issues:
        counts[issue.check] += 1
    return counts


st.set_page_config(page_title="docval user study")

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "submitted" not in st.session_state:
    st.session_state.submitted = False

st.title("Document structure check - user study")

# --- CONSENT TEXT --------------------------------------------------------
# Fill in the bracketed items - institution, contact - before this app is
# used with real participants. Check whether your institution also
# requires a separate signed consent step or an ethics approval number;
# this paragraph alone may not be sufficient on its own.
st.info(
    "**About this study.** This study is being conducted as part of a "
    "Master's research project at TU Ilmenau to "
    "evaluate a tool that checks the structural quality of Scientific " \
    "documents (Word, OpenOffice, LaTeX). "
    "Your participation is completely voluntary, and you may stop at any "
    "time without giving a reason and without any consequence. The "
    "document you upload will be analyzed only for its structural "
    "properties (headings, numbering, tables of contents, etc.) - its "
    "content is not reviewed, and the file itself is not stored. Your "
    "responses to the short questionnaire, together with the structural "
    "report, will be recorded anonymously and used only for this "
    "research; no personally identifying information is required. By "
    "downloading the document and proceeding, you confirm that you are 18 "
    "years or older and that you consent to participate under these "
    "conditions. If you have any questions, please contact "
    "muhammad.ahmad-sultan@tu-ilmenau.de"
)

st.write(
    "You will download a Word document that has several structural problems "
    "(headings, numbering, table of contents, and so on), fix them the way you think is best in "
    "Microsoft Word, and upload your result here. You will then see a report and "
    "be asked a few short questions about the experience."
)
# -------------------------------------------------------------------------

st.header("1. Download the document")
with open(TEMPLATE_PATH, "rb") as f:
    st.download_button(
        "Download the document to fix",
        data=f.read(),
        file_name=TEMPLATE_DOWNLOAD_NAME,
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

st.header("2. Upload your fixed document")
uploaded = st.file_uploader("Upload the .docx file once you are done",
                            type=["docx"])

issues = None
if uploaded is not None:
    try:
        issues = check_document(uploaded)
    except Exception as error:
        st.error(
            "This file could not be read. Please make sure it is a valid "
            ".docx file saved from Word, and try uploading it again.")
        # Shown so a read failure can be diagnosed from the app itself
        # instead of only from the Streamlit Cloud logs. Safe to display:
        # this is a parsing error about the uploaded file's structure, not
        # anything from the study's own configuration or secrets.
        st.caption(f"Technical detail: {type(error).__name__}: {error}")

if issues is not None:
    st.header("3. Your report")
    if not issues:
        st.success("No structural issues found.")
    else:
        st.warning(f"{len(issues)} issue(s) found.")
        for issue in issues:
            st.write(f"- **{CHECK_LABELS[issue.check]}**: {issue.message}")

    st.header("4. A few questions about using this tool")
    st.write("For each pair of words, click the number that best matches "
            "your impression: 1 is closest to the word on the left, 7 is "
            "closest to the word on the right.")

    with st.form("survey_form"):
        answers = []
        for left, right, _ in UEQ_ITEMS:
            label_col, scale_col = st.columns([2, 5])
            with label_col:
                st.markdown(f"**{left.capitalize()}** / **{right.capitalize()}**")
            with scale_col:
                answers.append(st.radio(
                    f"{left} to {right}", options=[1, 2, 3, 4, 5, 6, 7],
                    index=None, horizontal=True,
                    label_visibility="collapsed",
                    key=f"ueq_{left}_{right}"))

        participant_id = st.text_input(
            "Participant ID (filled in automatically; only change this if "
            "you were given a specific ID to use)",
            value=st.session_state.session_id[:8])

        submitted = st.form_submit_button("Submit")

    if submitted and any(answer is None for answer in answers):
        st.error("Please answer all eight questions before submitting.")
    elif submitted and not st.session_state.submitted:
        counts = issue_counts(issues)
        result = "Passed" if not issues else f"{len(issues)} issue(s)"
        pragmatic_score, hedonic_score = ueq_scores(answers)
        row = ([datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
                participant_id, uploaded.name, result, len(issues)]
               + [counts[check_id] for check_id in CHECK_LABELS]
               + answers
               + [pragmatic_score, hedonic_score])
        try:
            get_sheet().append_row(row, value_input_option="RAW")
            st.session_state.submitted = True
            st.success("Thank you - your submission has been recorded.")
        except Exception:
            st.error(
                "Your report was generated, but it could not be saved. "
                "Please let the study organiser know.")
    elif st.session_state.submitted:
        st.success("Thank you - your submission has already been recorded.")
