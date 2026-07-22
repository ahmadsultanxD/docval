"""
rules.py - Step 4: the checks that judge a document's structure.

The extractor turned the document into Blocks. Now we can finally ask the
questions this project exists for: are the headings real and properly nested,
are they auto-numbered, is there a table of contents, and so on.

Each check is one plain function. It takes three things and returns a list
of Issues - empty if the document passes:

    model      the document, as the Blocks an extractor produced
    structure  the Structure properties: WHAT the document must contain
    styles     the Styles properties: HOW it must be formatted

The checks do not know about Word, OpenOffice, or LaTeX; they only read the
representation. That is the whole point of the design: every format's
extractor output runs through these functions unchanged.

An Issue is deliberately minimal: which check fired, one sentence saying what
is wrong, and where. Severity and weighting belong to a later grading policy,
not here. The 'check' id is stable and machine-readable (the JSON reporter and
the CodeOcean integration will key on it); the message is for humans.

This file holds all eight checks of the plan, the section-order check, and
two more that the samples' equations motivated: real equation format, and
no uncaptioned inline images. Each check was verified against the sample
versions as it was added.
"""

import re
from dataclasses import dataclass
from typing import Optional

from config import DEFAULT_STRUCTURE, DEFAULT_STYLES
from model import DocModel


# A typed section number at the start of a heading text ("1. Introduction",
# "2.1 Methods"). Stripped before matching, so a document with typed heading
# numbers fails only the numbering check, not also the sections check.
_LEADING_NUMBER_RE = re.compile(r"^\s*\d+(\.\d+)*[.):]?\s*")


@dataclass
class Issue:
    """One thing wrong with the document, as found by one check."""

    check: str                        # stable id, e.g. "heading-hierarchy"
    message: str                      # one human sentence saying what is wrong
    block_index: Optional[int] = None  # where in the document, or None if the
                                       # problem is document-wide (e.g. no TOC)
    text: str = ""                    # short preview of the offending block,
                                       # so the reader can find the place


def _preview(block, limit=45):
    """A short piece of the block's text, to name the location in a message."""
    text = (block.text or "").strip()
    return text[:limit] + "..." if len(text) > limit else text


# --- Check 1: headings use real styles and nest without skipping levels ------

def check_heading_hierarchy(model: DocModel, structure, styles) -> list:
    """
    Two failure modes live here, and they need different handling.

    First: a document with NO real headings at all. The sample's fully faked
    version (v1) taught us this case - its "headings" are just bold text, so
    the extractor finds zero heading blocks, and a naive walk over the headings
    would find nothing wrong and wrongly pass. So an empty heading list is
    itself the finding.

    Second: skipped levels. How deep a heading may go is policy, so it comes
    from the Styles properties: the document starts at "first_level", and a
    heading may go at most "max_deeper_step" levels deeper than the heading
    before it (with the default step of 1: level 1 to level 2 is fine, level
    1 to level 3 skips level 2). Going back UP by any amount is fine -
    closing a subsection and starting a new chapter is normal. The first
    heading must be at first_level, which is the same rule if you imagine
    the level before the text.
    """
    issues = []
    headings = [b for b in model.blocks if b.type == "heading"]

    if not headings:
        issues.append(Issue(
            check="heading-hierarchy",
            message="No real heading styles found in the document; "
                    "headings appear to be typed as ordinary text.",
        ))
        return issues

    first_level = styles["headings"]["first_level"]
    max_step = styles["headings"]["max_deeper_step"]

    previous_level = first_level - 1  # imaginary level before the first heading
    for h in headings:
        if h.level > previous_level + max_step:
            issues.append(Issue(
                check="heading-hierarchy",
                message=f"Heading level {h.level} follows level "
                        f"{previous_level}, deeper than the allowed step "
                        f"of {max_step}.",
                block_index=h.index,
                text=_preview(h),
            ))
        previous_level = h.level

    return issues


# --- Check 2: headings are automatically numbered, not typed -----------------

def check_heading_numbering(model: DocModel, structure, styles) -> list:
    """
    The extractor already did the hard part: 'numbered' is True only if the
    heading is really auto-numbered (resolved through the style chain). Here
    we only report the headings where that is False. If such a heading's text
    starts with digits, the author almost certainly typed the number by hand,
    and the message says so, because that is more helpful than "not numbered".
    """
    issues = []
    for b in model.blocks:
        if b.type != "heading" or b.numbered:
            continue
        typed = (b.text or "").strip()[:1].isdigit()
        if typed:
            message = (f"Heading '{_preview(b)}' has a typed number "
                       "instead of automatic numbering.")
        else:
            message = f"Heading '{_preview(b)}' is not automatically numbered."
        issues.append(Issue(
            check="heading-numbering",
            message=message,
            block_index=b.index,
            text=_preview(b),
        ))
    return issues


# --- Check 3: a real table of contents field is present ----------------------

def check_toc_present(model: DocModel, structure, styles) -> list:
    """
    The extractor set toc_present only if it saw a real TOC field, so a typed
    imitation of a table of contents (v1's list of "1Introduction1" lines)
    does not count. Document-wide fact, so the issue has no block index.
    """
    if model.toc_present:
        return []
    return [Issue(
        check="toc-present",
        message="No real table of contents field found; "
                "a table of contents typed by hand does not count.",
    )]


# --- Check 4: the table of contents is linked to the headings -----------------

def check_toc_linked(model: DocModel, structure, styles) -> list:
    """
    A real table of contents does not merely list the headings, it links to
    them: each entry is a hyperlink whose anchor names a "_Toc" bookmark
    sitting on the heading it points at. So the test is resolution - every
    anchor the TOC uses must exist among the heading bookmarks. Anchors that
    do not resolve mean the TOC is stale: headings changed after it was
    generated, and it was never updated.

    If the document has no TOC at all, this check stays silent; that is
    check_toc_present's finding, and reporting it twice would be noise.
    """
    if not model.toc_present:
        return []

    if not model.toc_anchors:
        return [Issue(
            check="toc-linked",
            message="The table of contents has no links to the headings; "
                    "its entries do not point anywhere.",
        )]

    bookmarks = set(model.heading_bookmarks)
    dangling = [a for a in model.toc_anchors if a not in bookmarks]
    if dangling:
        return [Issue(
            check="toc-linked",
            message=f"{len(dangling)} of {len(model.toc_anchors)} table-of-"
                    "contents entries point at headings that no longer exist; "
                    "the table of contents is out of date.",
        )]
    return []


# --- Check 5: required sections are present -----------------------------------

def _normalize_heading(text):
    """Lowercase, trim, and drop a typed leading number, for name matching."""
    return _LEADING_NUMBER_RE.sub("", (text or "").strip().lower()).strip()


def _accepted_names(section):
    """
    The set of heading texts that satisfy one required section.

    "accept" is optional: a section written as just {"name": "Introduction"}
    is accepted under its own name, so a simple property file does not need
    to repeat the name as its own synonym. "accept" is only needed to ADD
    other accepted spellings, like a German translation.
    """
    synonyms = section.get("accept", [section["name"]])
    return {_normalize_heading(s) for s in synonyms}


def check_required_sections(model: DocModel, structure, styles) -> list:
    """
    Only real headings can satisfy a requirement: a section that exists as
    bold text is exactly the fake structure this tool exists to catch. That
    means a document with no real headings fails every requirement, on top
    of the hierarchy check's finding - deliberately so. Each missing section
    is its own piece of information for grading, and nothing gets skipped
    just because another check already fired.

    An empty sections list in the Structure properties means no section
    requirements at all: any sections are fine, as long as the document is
    properly structured (the Styles rules still apply in full).

    Both sides of the comparison go through the same normalization, so the
    section list stays forgiving about case and stray spaces when it is
    edited in the property file.
    """
    present = {_normalize_heading(b.text)
               for b in model.blocks if b.type == "heading"}
    issues = []
    for section in structure["sections"]:
        accepted = _accepted_names(section)
        if present & accepted:
            continue
        name = section["name"]
        issues.append(Issue(
            check="required-sections",
            message=f"Required section '{name}' not found among "
                    "the document's headings.",
        ))
    return issues


def check_section_order(model: DocModel, structure, styles) -> list:
    """
    The Structure properties list the sections in the order they are
    expected to appear, so a section found earlier in the document than a
    section listed before it is an issue. Only the sections that actually
    exist are compared - a missing section is check_required_sections'
    finding, and reporting it twice would be noise.
    """
    # Where in the document does each configured section first appear?
    heading_positions = []
    for position, block in enumerate(model.blocks):
        if block.type == "heading":
            heading_positions.append((position, _normalize_heading(block.text)))

    found = []  # (position in document, section name), in configured order
    for section in structure["sections"]:
        accepted = _accepted_names(section)
        for position, heading_text in heading_positions:
            if heading_text in accepted:
                found.append((position, section["name"]))
                break

    issues = []
    for earlier, later in zip(found, found[1:]):
        earlier_position, earlier_name = earlier
        later_position, later_name = later
        if later_position < earlier_position:
            issues.append(Issue(
                check="section-order",
                message=f"Section '{later_name}' appears before "
                        f"'{earlier_name}', but is expected after it.",
            ))
    return issues


# --- Check 6: lists use real list formatting, not typed markers --------------

def check_list_formatting(model: DocModel, structure, styles) -> list:
    """
    The extractor marks a paragraph as a real list item when it carries real
    numbering without being a heading, and as a typed one when its text merely
    starts with a list marker ("-", "1.", "RQ1:"). Here we only report the
    typed ones. The difference is more than looks: in a real list the labels
    come from the numbering definition, so inserting or reordering items
    renumbers them automatically - typed markers silently go stale.
    """
    issues = []
    for b in model.blocks:
        if b.type != "list_item" or b.real:
            continue
        first = (b.text or "").strip()[:1]
        if first.isdigit() or first.isalpha():
            message = (f"List item '{_preview(b)}' has a typed number or "
                       "label instead of automatic list numbering.")
        else:
            message = (f"List item '{_preview(b)}' has a typed bullet "
                       "instead of real list formatting.")
        issues.append(Issue(
            check="list-formatting",
            message=message,
            block_index=b.index,
            text=_preview(b),
        ))
    return issues


# --- Checks 7 and 8: every table and figure has a real caption, correctly placed

def _caption_matches(block, kind):
    """True if this block is a caption of the given kind, real or typed."""
    return block is not None and block.type == "caption" and block.kind == kind


def _caption_issues(model, kind, expected_position, check_id):
    """
    The shared test behind the table and figure caption checks: the block
    directly on the expected side ("above" or "below", from the Styles
    properties) must be a real caption of the right kind. The test is plain
    adjacency, with nothing in between. Three ways to fail, told apart so
    the message can say what actually happened: a typed caption in the
    right place, a caption on the wrong side, or no caption at all.

    Inline figures (images pasted into a line of text) are left out,
    because check_inline_images already owns them and flagging the same
    image twice would be noise.
    """
    issues = []
    other_position = "below" if expected_position == "above" else "above"

    for i, b in enumerate(model.blocks):
        if b.type != kind:
            continue
        if kind == "figure" and b.inline:
            continue

        above = model.blocks[i - 1] if i > 0 else None
        below = model.blocks[i + 1] if i + 1 < len(model.blocks) else None
        expected_side = above if expected_position == "above" else below
        other_side = below if expected_position == "above" else above

        if _caption_matches(expected_side, kind):
            if not expected_side.real:
                issues.append(Issue(
                    check=check_id,
                    message=f"The caption {expected_position} this {kind} "
                            "is typed text, not a real caption with "
                            "automatic numbering.",
                    block_index=b.index, text=_preview(expected_side),
                ))
        elif _caption_matches(other_side, kind):
            issues.append(Issue(
                check=check_id,
                message=f"This {kind}'s caption sits {other_position} it; "
                        f"a {kind} caption belongs directly "
                        f"{expected_position} it.",
                block_index=b.index, text=_preview(other_side),
            ))
        else:
            issues.append(Issue(
                check=check_id,
                message=f"This {kind} has no caption directly "
                        f"{expected_position} it.",
                block_index=b.index,
            ))
    return issues


def check_table_captions(model: DocModel, structure, styles) -> list:
    """Every table has a real caption on the configured side (above, by
    scientific convention and by default)."""
    return _caption_issues(model, "table",
                           styles["captions"]["table_position"],
                           "table-caption")


def check_figure_captions(model: DocModel, structure, styles) -> list:
    """Every figure has a real caption on the configured side (below, by
    scientific convention and by default)."""
    return _caption_issues(model, "figure",
                           styles["captions"]["figure_position"],
                           "figure-caption")


# --- Check 9: equations use the real equation format --------------------------

def check_equation_format(model: DocModel, structure, styles) -> list:
    """
    A real equation is an OMML math object: Word can renumber it, style it,
    and a screen reader can read it. A formula typed as ordinary text only
    looks like an equation. The extractor already decided which is which
    (including inside footnotes, where the samples keep theirs); here we
    report the typed ones.
    """
    issues = []
    for b in model.blocks:
        if b.type != "equation" or b.real:
            continue
        issues.append(Issue(
            check="equation-format",
            message=f"Equation '{_preview(b)}' is typed as ordinary text "
                    "instead of using the equation format.",
            block_index=b.index,
            text=_preview(b),
        ))
    return issues


# --- Check 10: no uncaptioned images pasted into the text ---------------------

def check_inline_images(model: DocModel, structure, styles) -> list:
    """
    An image sitting inside a line of text, with no caption anywhere next to
    it, is suspicious: that is how a screenshot of an equation or a symbol
    usually arrives. We cannot read the pixels to prove what the image shows,
    so the message says what we actually know - an inline image without a
    caption - rather than claiming certainty.
    """
    issues = []
    for i, b in enumerate(model.blocks):
        if b.type != "figure" or not b.inline:
            continue
        neighbours = model.blocks[max(0, i - 1):i + 2]
        captioned = any(n.type == "caption" for n in neighbours)
        if captioned:
            continue
        issues.append(Issue(
            check="inline-image",
            message="An image is pasted inside the text without a caption; "
                    "possibly a picture of an equation or symbol.",
            block_index=b.index,
            text=_preview(b),
        ))
    return issues


# --- the engine ---------------------------------------------------------------

# Every check, paired with its stable id, in the order they run and report.
# The id is what the config's "checks" table and the JSON output key on, so
# it must never change once published, even if the function is renamed.
CHECKS = [
    ("heading-hierarchy", check_heading_hierarchy),
    ("heading-numbering", check_heading_numbering),
    ("toc-present",       check_toc_present),
    ("toc-linked",        check_toc_linked),
    ("required-sections", check_required_sections),
    ("section-order",     check_section_order),
    ("list-formatting",   check_list_formatting),
    ("table-caption",     check_table_captions),
    ("figure-caption",    check_figure_captions),
    ("equation-format",   check_equation_format),
    ("inline-image",      check_inline_images),
]


def enabled_checks(styles=None) -> list:
    """The ids of the checks the Styles leave enabled, in run order."""
    if styles is None:
        styles = DEFAULT_STYLES
    switches = styles.get("checks", {})
    return [check_id for check_id, _ in CHECKS if switches.get(check_id, True)]


def run_checks(model: DocModel, structure=None, styles=None) -> list:
    """
    Run every enabled check and return all issues in one list.

    Without property sets the built-in defaults apply, so callers that do
    not care about configuration can keep calling run_checks(model).
    """
    if structure is None:
        structure = DEFAULT_STRUCTURE
    if styles is None:
        styles = DEFAULT_STYLES
    enabled = set(enabled_checks(styles))
    issues = []
    for check_id, check in CHECKS:
        if check_id in enabled:
            issues.extend(check(model, structure, styles))
    return issues


# A small demonstration: run the checks against a sample document, so this
# file can be tried on its own before the real reporter exists.
def _demo():
    import sys
    from word_extractor import extract

    path = sys.argv[1] if len(sys.argv) > 1 else "Sample Documents/Word/Assignment_v8.docx"
    print(f"Checking: {path}\n")

    model = extract(path)
    issues = run_checks(model)

    if not issues:
        print("No issues found.")
        return
    print(f"Found {len(issues)} issue(s):\n")
    for issue in issues:
        where = f"block {issue.block_index}" if issue.block_index is not None else "document"
        print(f"  [{issue.check}] ({where}) {issue.message}")


if __name__ == "__main__":
    _demo()
