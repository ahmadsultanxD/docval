"""
test_rules.py - each check on its own, against documents built by hand.

The ladder tests prove the checks behave correctly on real documents, but
real documents cannot show every case: the samples contain no caption on
the wrong side, no stale table of contents, no typed bullet. Those faults
are easy to build directly out of Blocks, which is what these tests do.

Because a Block is only a small container of named fields, a "document"
here is a handful of lines and no file at all - so these tests also state,
in the plainest way available, what each check considers wrong.
"""

import pytest

from conftest import NO_SECTIONS

from model import Block, DocModel
import rules


def document(*blocks, **facts):
    """A DocModel from the blocks given, numbered in the order written."""
    model = DocModel(**facts)
    for index, block in enumerate(blocks):
        block.index = index
        model.blocks.append(block)
    return model


def heading(level, text="A Heading", numbered=True, **extra):
    return Block(index=0, type="heading", text=text, level=level,
                 numbered=numbered, **extra)


def run(check, model, structure=NO_SECTIONS, styles=None):
    """Run one check with the built-in styles unless told otherwise."""
    from config import DEFAULT_STYLES

    return check(model, structure, styles or DEFAULT_STYLES)


# --- heading hierarchy --------------------------------------------------------

def test_no_real_headings_is_itself_the_finding():
    """
    A document whose headings are only bold text produces no heading blocks
    at all. Walking an empty list would find nothing wrong and pass, which
    is the opposite of the truth.
    """
    model = document(Block(index=0, type="paragraph", text="Introduction"))
    assert len(run(rules.check_heading_hierarchy, model)) == 1


def test_a_skipped_level_is_reported():
    model = document(heading(1), heading(3))
    assert len(run(rules.check_heading_hierarchy, model)) == 1


def test_going_back_up_any_number_of_levels_is_fine():
    """Closing a subsection to start a new chapter is normal writing."""
    model = document(heading(1), heading(2), heading(3), heading(1))
    assert run(rules.check_heading_hierarchy, model) == []


def test_the_allowed_step_comes_from_the_styles():
    """A course that permits jumping a level says so in its property file."""
    import copy

    from config import DEFAULT_STYLES

    lenient = copy.deepcopy(DEFAULT_STYLES)
    lenient["headings"]["max_deeper_step"] = 2
    model = document(heading(1), heading(3))
    assert run(rules.check_heading_hierarchy, model, styles=lenient) == []


# --- heading numbering --------------------------------------------------------

def test_an_unnumbered_heading_is_reported_in_word():
    """In Word, numbering has to be switched on, so its absence is a fault."""
    model = document(heading(1, "Introduction", numbered=False))
    assert len(run(rules.check_heading_numbering, model)) == 1


def test_an_unnumbered_heading_is_allowed_where_the_format_numbers_itself():
    """In LaTeX it is a choice, and the extractor says so on the block."""
    model = document(heading(1, "Abstract", numbered=False,
                             numbering_optional=True))
    assert run(rules.check_heading_numbering, model) == []


def test_a_typed_number_is_reported_in_every_format():
    """The one fault that is a fault everywhere."""
    model = document(heading(1, "2. Related Work", numbered=False,
                             numbering_optional=True))
    issues = run(rules.check_heading_numbering, model)
    assert len(issues) == 1 and "typed number" in issues[0].message


# --- table of contents --------------------------------------------------------

def test_a_missing_table_of_contents_is_reported():
    assert len(run(rules.check_toc_present, document())) == 1


def test_toc_linked_stays_quiet_when_there_is_no_toc_at_all():
    """That is check_toc_present's finding; reporting it twice is noise."""
    assert run(rules.check_toc_linked, document()) == []


def test_a_toc_with_no_links_is_reported():
    model = document(toc_present=True, heading_bookmarks=["_Toc1"],
                     toc_anchors=[])
    assert len(run(rules.check_toc_linked, model)) == 1


def test_a_toc_pointing_at_a_heading_that_no_longer_exists_is_reported():
    """The stale table of contents: edited headings, ungenerated contents."""
    model = document(toc_present=True,
                     heading_bookmarks=["_Toc1", "_Toc2"],
                     toc_anchors=["_Toc1", "_Toc2", "_Toc3"])
    assert len(run(rules.check_toc_linked, model)) == 1


def test_a_toc_whose_entries_all_resolve_is_accepted():
    model = document(toc_present=True,
                     heading_bookmarks=["_Toc1", "_Toc2"],
                     toc_anchors=["_Toc1", "_Toc2"])
    assert run(rules.check_toc_linked, model) == []


# --- required sections and their order ----------------------------------------

SECTIONS = {"sections": [
    {"name": "Introduction", "accept": ["introduction", "einleitung"]},
    {"name": "Methodology"},
    {"name": "Results"},
]}


def test_a_missing_section_is_reported():
    model = document(heading(1, "Introduction"), heading(1, "Results"))
    issues = run(rules.check_required_sections, model, structure=SECTIONS)
    assert len(issues) == 1 and "Methodology" in issues[0].message


def test_matching_ignores_case_and_a_typed_number():
    model = document(heading(1, "1. INTRODUCTION"), heading(1, "Methodology"),
                     heading(1, "  results  "))
    assert run(rules.check_required_sections, model, structure=SECTIONS) == []


def test_a_synonym_satisfies_a_section():
    """A German-language document passes the same requirement."""
    model = document(heading(1, "Einleitung"), heading(1, "Methodology"),
                     heading(1, "Results"))
    assert run(rules.check_required_sections, model, structure=SECTIONS) == []


def test_accept_is_optional_and_defaults_to_the_name():
    """A section written as just {"name": ...} is accepted under that name."""
    model = document(heading(1, "Introduction"), heading(1, "Methodology"),
                     heading(1, "Results"))
    assert run(rules.check_required_sections, model, structure=SECTIONS) == []


def test_only_real_headings_can_satisfy_a_section():
    """A section that exists as bold text is exactly the faked structure
    this tool is for."""
    model = document(Block(index=0, type="paragraph", text="Introduction"))
    issues = run(rules.check_required_sections, model, structure=SECTIONS)
    assert len(issues) == 3


def test_an_empty_section_list_switches_section_checking_off():
    """Any sections are then fine; the style rules still apply in full."""
    model = document(Block(index=0, type="paragraph", text="Whatever"))
    assert run(rules.check_required_sections, model, structure=NO_SECTIONS) == []


def test_sections_out_of_order_are_reported():
    model = document(heading(1, "Introduction"), heading(1, "Results"),
                     heading(1, "Methodology"))
    assert len(run(rules.check_section_order, model, structure=SECTIONS)) == 1


def test_sections_in_order_are_accepted():
    model = document(heading(1, "Introduction"), heading(1, "Methodology"),
                     heading(1, "Results"))
    assert run(rules.check_section_order, model, structure=SECTIONS) == []


def test_a_missing_section_is_not_also_an_order_problem():
    """That is check_required_sections' finding."""
    model = document(heading(1, "Introduction"), heading(1, "Results"))
    assert run(rules.check_section_order, model, structure=SECTIONS) == []


# --- lists --------------------------------------------------------------------

def test_a_typed_list_marker_is_reported():
    model = document(Block(index=0, type="list_item", text="- an item",
                           real=False))
    assert len(run(rules.check_list_formatting, model)) == 1


def test_a_real_list_item_is_accepted():
    model = document(Block(index=0, type="list_item", text="an item",
                           real=True))
    assert run(rules.check_list_formatting, model) == []


# --- captions -----------------------------------------------------------------

def caption(kind, real=True, text="Table 1: A caption"):
    return Block(index=0, type="caption", kind=kind, real=real, text=text)


def test_a_table_caption_belongs_above_the_table():
    model = document(caption("table"), Block(index=0, type="table"))
    assert run(rules.check_table_captions, model) == []


def test_a_table_caption_below_the_table_is_reported():
    model = document(Block(index=0, type="table"), caption("table"))
    issues = run(rules.check_table_captions, model)
    assert len(issues) == 1 and "below" in issues[0].message


def test_a_table_with_no_caption_is_reported():
    model = document(Block(index=0, type="table"))
    assert len(run(rules.check_table_captions, model)) == 1


def test_a_typed_table_caption_is_reported():
    model = document(caption("table", real=False), Block(index=0, type="table"))
    issues = run(rules.check_table_captions, model)
    assert len(issues) == 1 and "typed text" in issues[0].message


def test_a_figure_caption_belongs_below_the_figure():
    model = document(Block(index=0, type="figure"), caption("figure"))
    assert run(rules.check_figure_captions, model) == []


def test_a_figure_caption_above_the_figure_is_reported():
    model = document(caption("figure"), Block(index=0, type="figure"))
    assert len(run(rules.check_figure_captions, model)) == 1


def test_the_expected_side_comes_from_the_styles():
    """A course with a different house style says so in its property file."""
    import copy

    from config import DEFAULT_STYLES

    flipped = copy.deepcopy(DEFAULT_STYLES)
    flipped["captions"]["figure_position"] = "above"
    model = document(caption("figure"), Block(index=0, type="figure"))
    assert run(rules.check_figure_captions, model, styles=flipped) == []


def test_an_inline_figure_is_left_to_the_inline_image_check():
    """Flagging the same image from two checks would be noise."""
    model = document(Block(index=0, type="figure", inline=True,
                           text="see the symbol here"))
    assert run(rules.check_figure_captions, model) == []


# --- equations and pasted images ----------------------------------------------

def test_a_typed_equation_is_reported():
    model = document(Block(index=0, type="equation", text="F1 = 2*P*R",
                           real=False))
    assert len(run(rules.check_equation_format, model)) == 1


def test_a_real_equation_is_accepted():
    model = document(Block(index=0, type="equation", text="F1", real=True))
    assert run(rules.check_equation_format, model) == []


def test_an_uncaptioned_inline_image_is_reported():
    """How a pasted picture of an equation usually arrives."""
    model = document(Block(index=0, type="figure", inline=True,
                           text="as shown mid-sentence"))
    assert len(run(rules.check_inline_images, model)) == 1


def test_a_captioned_inline_image_is_accepted():
    model = document(Block(index=0, type="figure", inline=True, text="here"),
                     caption("figure"))
    assert run(rules.check_inline_images, model) == []


# --- the engine ----------------------------------------------------------------

def test_a_check_can_be_switched_off():
    """A course that does not require a table of contents says so."""
    import copy

    from config import DEFAULT_STYLES

    styles = copy.deepcopy(DEFAULT_STYLES)
    styles["checks"]["toc-present"] = False
    issues = rules.run_checks(document(), NO_SECTIONS, styles)
    assert "toc-present" not in {issue.check for issue in issues}


def test_enabled_checks_lists_what_will_run():
    import copy

    from config import DEFAULT_STYLES

    styles = copy.deepcopy(DEFAULT_STYLES)
    styles["checks"]["toc-present"] = False
    enabled = rules.enabled_checks(styles)
    assert "toc-present" not in enabled and "heading-hierarchy" in enabled


def test_every_check_has_a_stable_id():
    """The ids are what the property files and the JSON output key on."""
    ids = [check_id for check_id, _ in rules.CHECKS]
    assert len(ids) == len(set(ids))
    assert "heading-hierarchy" in ids and "section-order" in ids
