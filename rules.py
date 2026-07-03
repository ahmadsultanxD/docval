"""
rules.py - Step 4: the checks that judge a document's structure.

The extractor turned the document into Blocks. Now we can finally ask the
questions this project exists for: are the headings real and properly nested,
are they auto-numbered, is there a table of contents, and so on.

Each check is one plain function. It takes the DocModel, looks at the blocks
or the document-wide facts, and returns a list of Issues - empty if the
document passes. The checks do not know about Word, OpenOffice, or LaTeX;
they only read the representation. That is the whole point of the design:
when the .odt and .tex extractors exist, these functions run on their output
unchanged.

An Issue is deliberately minimal: which check fired, one sentence saying what
is wrong, and where. Severity and weighting belong to a later grading policy,
not here. The 'check' id is stable and machine-readable (the JSON reporter and
the CodeOcean integration will key on it); the message is for humans.

This file holds all eight checks of the plan, plus two beyond the original
eight that the samples' equations motivated: real equation format, and no
uncaptioned inline images. Each check was verified against the sample
versions as it was added.
"""

import re
from dataclasses import dataclass
from typing import Optional

from model import DocModel


# The sections a scientific document must contain. Each entry is the
# canonical name (used in the issue message) and the set of heading texts
# that satisfy it, so a German-language document passes the same check
# ("Einleitung" satisfies "Introduction"). This is deliberately pure data:
# in the cross-cutting phase it moves into the config file unchanged, and
# adding or removing a requirement is editing this list, not code. The
# German synonyms are unverified until a German-text sample exists.
REQUIRED_SECTIONS = [
    ("Introduction",          {"introduction", "einleitung"}),
    ("State of Research",     {"state of research", "related work",
                               "stand der forschung", "verwandte arbeiten"}),
    ("Theoretical Framework", {"theoretical framework", "theoretischer rahmen",
                               "theoretische grundlagen"}),
    ("Methodology",           {"methodology", "methods", "methodik", "methoden"}),
    ("Results",               {"results", "ergebnisse"}),
    ("Discussion",            {"discussion", "diskussion"}),
    ("Conclusion",            {"conclusion", "fazit", "schlussfolgerung"}),
    ("References",            {"references", "bibliography",
                               "literaturverzeichnis", "literatur"}),
]

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

def check_heading_hierarchy(model: DocModel) -> list:
    """
    Two failure modes live here, and they need different handling.

    First: a document with NO real headings at all. The sample's fully faked
    version (v1) taught us this case - its "headings" are just bold text, so
    the extractor finds zero heading blocks, and a naive walk over the headings
    would find nothing wrong and wrongly pass. So an empty heading list is
    itself the finding.

    Second: skipped levels. A heading may go at most one level deeper than the
    heading before it (level 1 to level 2 is fine, level 1 to level 3 skips
    level 2). Going back UP by any amount is fine - closing a subsection and
    starting a new chapter is normal. The first heading of the document must
    be level 1, which is the same rule if you imagine level 0 before the text.
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

    previous_level = 0  # imaginary level before the first heading
    for h in headings:
        if h.level > previous_level + 1:
            issues.append(Issue(
                check="heading-hierarchy",
                message=f"Heading level {h.level} follows level "
                        f"{previous_level}, skipping level {previous_level + 1}.",
                block_index=h.index,
                text=_preview(h),
            ))
        previous_level = h.level

    return issues


# --- Check 2: headings are automatically numbered, not typed -----------------

def check_heading_numbering(model: DocModel) -> list:
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

def check_toc_present(model: DocModel) -> list:
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

def check_toc_linked(model: DocModel) -> list:
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


def check_required_sections(model: DocModel) -> list:
    """
    Only real headings can satisfy a requirement: a section that exists as
    bold text is exactly the fake structure this tool exists to catch. That
    means a document with no real headings fails every requirement, on top
    of the hierarchy check's finding - deliberately so. Each missing section
    is its own piece of information for grading, and nothing gets skipped
    just because another check already fired.

    Both sides of the comparison go through the same normalization, so the
    requirement list stays forgiving about case and stray spaces when it is
    edited by hand (and later, in the config file).
    """
    present = {_normalize_heading(b.text)
               for b in model.blocks if b.type == "heading"}
    issues = []
    for canonical, synonyms in REQUIRED_SECTIONS:
        accepted = {_normalize_heading(s) for s in synonyms}
        if present & accepted:
            continue
        issues.append(Issue(
            check="required-sections",
            message=f"Required section '{canonical}' not found among "
                    "the document's headings.",
        ))
    return issues


# --- Check 6: lists use real list formatting, not typed markers --------------

def check_list_formatting(model: DocModel) -> list:
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


def check_table_captions(model: DocModel) -> list:
    """
    Scientific convention places a table's caption ABOVE the table, and the
    samples follow it strictly: the caption is the block immediately before,
    with nothing in between. So the test is plain adjacency. Three ways to
    fail, told apart so the message can say what actually happened: a typed
    caption in the right place, a caption on the wrong side, or no caption
    at all.
    """
    issues = []
    for i, b in enumerate(model.blocks):
        if b.type != "table":
            continue
        above = model.blocks[i - 1] if i > 0 else None
        below = model.blocks[i + 1] if i + 1 < len(model.blocks) else None

        if _caption_matches(above, "table"):
            if not above.real:
                issues.append(Issue(
                    check="table-caption",
                    message="The caption above this table is typed text, "
                            "not a real caption with automatic numbering.",
                    block_index=b.index, text=_preview(above),
                ))
        elif _caption_matches(below, "table"):
            issues.append(Issue(
                check="table-caption",
                message="This table's caption sits below the table; "
                        "a table caption belongs directly above it.",
                block_index=b.index, text=_preview(below),
            ))
        else:
            issues.append(Issue(
                check="table-caption",
                message="This table has no caption directly above it.",
                block_index=b.index,
            ))
    return issues


def check_figure_captions(model: DocModel) -> list:
    """
    The mirror image of the table check: a figure's caption belongs directly
    BELOW the figure. Inline figures (images pasted into a line of text) are
    left out here, because check_inline_images already owns them and flagging
    the same image twice would be noise.
    """
    issues = []
    for i, b in enumerate(model.blocks):
        if b.type != "figure" or b.inline:
            continue
        above = model.blocks[i - 1] if i > 0 else None
        below = model.blocks[i + 1] if i + 1 < len(model.blocks) else None

        if _caption_matches(below, "figure"):
            if not below.real:
                issues.append(Issue(
                    check="figure-caption",
                    message="The caption below this figure is typed text, "
                            "not a real caption with automatic numbering.",
                    block_index=b.index, text=_preview(below),
                ))
        elif _caption_matches(above, "figure"):
            issues.append(Issue(
                check="figure-caption",
                message="This figure's caption sits above the figure; "
                        "a figure caption belongs directly below it.",
                block_index=b.index, text=_preview(above),
            ))
        else:
            issues.append(Issue(
                check="figure-caption",
                message="This figure has no caption directly below it.",
                block_index=b.index,
            ))
    return issues


# --- Check 9: equations use the real equation format --------------------------

def check_equation_format(model: DocModel) -> list:
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

def check_inline_images(model: DocModel) -> list:
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

# The checks that are implemented so far, in the order they run and report.
# Later, the config file decides which of these are active; for now, all.
CHECKS = [
    check_heading_hierarchy,
    check_heading_numbering,
    check_toc_present,
    check_toc_linked,
    check_required_sections,
    check_list_formatting,
    check_table_captions,
    check_figure_captions,
    check_equation_format,
    check_inline_images,
]


def run_checks(model: DocModel) -> list:
    """Run every active check and return all issues in one list."""
    issues = []
    for check in CHECKS:
        issues.extend(check(model))
    return issues


# A small demonstration: run the checks against a sample document, so this
# file can be tried on its own before the real reporter exists.
def _demo():
    import sys
    from extractor import extract

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
