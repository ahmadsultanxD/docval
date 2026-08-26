"""
patterns.py - recognizing structure that was TYPED rather than built.

Real structure looks different in every format: Word marks a real caption
with a SEQ field, LaTeX with a \\caption command. But FAKED structure looks
the same everywhere, because it is just text imitating the real thing:
"Table 1: ..." typed above a table, "RQ1:" typed in front of a research
question, a formula typed with keyboard characters. So the patterns that
recognize typed structure are shared by every extractor, built from the
same config, and live here rather than in any one format's extractor.
"""

import re


def compile_patterns(styles):
    """
    Build the language-dependent lookups from the Styles property set:
    which words label which caption kind, and what a typed list marker
    looks like.

    The caption labels are localized ("Table"/"Tabelle"), so the styles
    list the accepted words per kind; the same words recognize typed
    captions ("Table 1 ..." with nothing real behind it). A typed list
    marker is a bullet character, a number like "1." or "1)", a lowercase
    letter like "a)" (lowercase only, because a capital with a period would
    match initials in a references list, "A. Smith"), or one of the
    configured labels ("RQ1:") - in a real list that label comes from the
    format's numbering machinery and never appears in the text; typed as
    ordinary text it marks a fake.
    """
    seq_labels = {}
    for kind, labels in styles["captions"]["labels"].items():
        for label in labels:
            seq_labels[label.lower()] = kind
    faked_caption_re = re.compile(
        r"^\s*(%s)\s+\d+" % "|".join(seq_labels), re.I)
    typed_list_re = re.compile(
        r"^\s*(?:[-•*·▪–]\s+|\d+[.)]\s+|[a-z][.)]\s+|(?:%s)\d+[.:)]?\s*)"
        % "|".join(styles["lists"]["labels"]))
    return seq_labels, faked_caption_re, typed_list_re


# A typed equation: an "=" with a math operator somewhere around it, in text
# that has no real math object behind it. Deliberately conservative - "=" on
# its own appears in ordinary prose ("p = 0.05"), so we also require one of
# the distinctly mathematical symbols. Two characters are left out of the
# operator class on purpose: the hyphen, because it is everywhere in prose,
# and the forward slash, because it is everywhere in file paths, URLs and
# dates, where an "=" is often nearby ("?width=2&file=a/b.jpg"). A genuinely
# typed formula almost always carries another operator besides the slash.
# This heuristic is UNVERIFIED against a labeled Word sample; the .docx set
# contains no faked equation.
TYPED_EQUATION_RE = re.compile(
    r"=[^=]*[+*·∙×^√∑∫≤≥≈]|[+*·∙×^√∑∫≤≥≈][^=]*="
)
