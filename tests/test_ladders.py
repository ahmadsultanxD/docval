"""
test_ladders.py - the labeled sample documents, turned into assertions.

The sample versions are the heart of how this project is verified. Each one
adds or fixes exactly one structural feature, so a check must start passing
at the version where its feature appears and not before. Until now that was
confirmed by reading the output by hand after every change; here it becomes
something the machine confirms in a second.

The expectations below are the labels of the sample set, written down. If a
change to an extractor or a rule makes one of them wrong, that is either a
bug or a deliberate decision that has to be recorded here on purpose.
"""

import pytest

from conftest import LATEX_SAMPLES, ODT_SAMPLES, WORD_SAMPLES, issue_counts


# What each Word version should report. The ladder reads downwards: v1 is
# faked throughout, and each later version fixes one more thing until v8,
# which is fully structured and clean.
WORD_LADDER = {
    "v1": {                                  # nothing is real: the headings
        "heading-hierarchy": 1,              # are numbered list items, the
        "toc-present": 1,                    # table of contents is typed,
        "list-formatting": 3,                # and so are the RQ items
    },
    "v2": {                                  # real heading styles arrive,
        "heading-numbering": 13,             # but without automatic numbering
        "toc-present": 1,
        "list-formatting": 3,
    },
    "v2a": {                                 # content arrives, including a
        "heading-numbering": 13,             # PICTURE of an equation with no
        "toc-present": 1,                    # caption - the figure-caption
        "list-formatting": 3,                # check is what catches it
        "figure-caption": 1,
    },
    "v3": {                                  # the picture becomes a real
        "heading-numbering": 13,             # equation, so figure-caption
        "toc-present": 1,                    # goes quiet again
        "list-formatting": 3,
    },
    "v4": {                                  # the equation moves into a
        "heading-numbering": 13,             # footnote and stays real
        "toc-present": 1,
        "list-formatting": 3,
    },
    "v5": {                                  # heading bookmarks appear, but
        "heading-numbering": 13,             # still no table of contents
        "toc-present": 1,
        "list-formatting": 3,
    },
    "v6": {                                  # a real, linked table of
        "heading-numbering": 13,             # contents: toc-present is quiet
        "list-formatting": 3,
    },
    "v7": {                                  # automatic heading numbering:
        "list-formatting": 3,                # only the typed RQs are left
    },
    "v8": {},                                # fully structured, nothing wrong
    "v9": {                                  # headings edited after the table
        "toc-linked": 1,                     # of contents was generated, so
    },                                       # one entry now points nowhere
}


# The LaTeX versions mirror the Word ones fault for fault, so they expect
# exactly the same results. The faults are written the way each format
# fakes them: where the Word versions have heading styles with the
# numbering switched off and the number typed in, the LaTeX ones turn
# secnumdepth down and type the number into the section title.
#
# Only v9 has no LaTeX counterpart. It is a table of contents left stale
# after its headings were edited, which cannot happen in LaTeX: the table
# of contents is generated from the sectioning commands every time the
# document is built.
LATEX_LADDER = {version: expected
                for version, expected in WORD_LADDER.items()
                if version != "v9"}


# The OpenDocument versions are the same documents again, so they expect the
# same results throughout - v9 included, because a table of contents left
# stale after its headings were edited is something OpenDocument can have
# just as Word can.
ODT_LADDER = dict(WORD_LADDER)


@pytest.mark.parametrize("version, expected", sorted(WORD_LADDER.items()))
def test_word_ladder(version, expected):
    """Each Word version reports exactly the issues its label says it should."""
    import word_extractor

    model = word_extractor.extract(str(WORD_SAMPLES / f"Assignment_{version}.docx"))
    assert issue_counts(model) == expected


@pytest.mark.parametrize("version, expected", sorted(LATEX_LADDER.items()))
def test_latex_ladder(version, expected):
    """Each LaTeX version reports exactly the issues its label says it should."""
    import latex_extractor

    model = latex_extractor.extract(str(LATEX_SAMPLES / f"Assignment_{version}.tex"))
    assert issue_counts(model) == expected


@pytest.mark.parametrize("version, expected", sorted(ODT_LADDER.items()))
def test_odt_ladder(version, expected):
    """Each OpenDocument version reports exactly what its label says."""
    import odt_extractor

    model = odt_extractor.extract(str(ODT_SAMPLES / f"Assignment_{version}.odt"))
    assert issue_counts(model) == expected


@pytest.mark.parametrize("version", sorted(LATEX_LADDER))
def test_every_format_agrees(version):
    """
    The same document in three formats gives the same verdict, exactly.

    This is the promise the whole architecture rests on: one set of rules,
    written once, judging every format. Each format fakes its structure in
    its own way, and the extractors are what absorb that difference - by
    the time the rules see a document, nothing about its format is left.
    """
    import latex_extractor
    import odt_extractor
    import word_extractor

    word = issue_counts(word_extractor.extract(
        str(WORD_SAMPLES / f"Assignment_{version}.docx")))
    latex = issue_counts(latex_extractor.extract(
        str(LATEX_SAMPLES / f"Assignment_{version}.tex")))
    odt = issue_counts(odt_extractor.extract(
        str(ODT_SAMPLES / f"Assignment_{version}.odt")))
    assert word == latex == odt


def test_fully_structured_documents_are_clean():
    """The finished version of the sample passes every check, in every format."""
    import latex_extractor
    import odt_extractor
    import word_extractor

    assert issue_counts(word_extractor.extract(
        str(WORD_SAMPLES / "Assignment_v8.docx"))) == {}
    assert issue_counts(latex_extractor.extract(
        str(LATEX_SAMPLES / "Assignment_v8.tex"))) == {}
    assert issue_counts(odt_extractor.extract(
        str(ODT_SAMPLES / "Assignment_v8.odt"))) == {}
