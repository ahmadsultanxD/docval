"""
test_odt_constructs.py - the OpenDocument details that are easy to get wrong.

The ladder tests prove the extractor reads the sample documents correctly.
These tests pin down the two mechanisms underneath, because both are
invisible in the output until they break something: how text is read out of
an element, and how a heading's numbering is resolved through its styles.

Both are exercised on small pieces of XML rather than whole .odt files, so
each test shows the exact structure it is about.
"""

from lxml import etree

import odt_extractor as odt

# The namespaces an OpenDocument body uses, declared once so the fragments
# below can be written the way they appear in a real file.
NAMESPACES = (
    'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
    'xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" '
    'xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" '
    'xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible-draw:1.0"'
)


def parse_all(xml):
    """
    Parse pieces of body XML and return them.

    They are wrapped in a holder element that declares the namespaces, so
    each fragment can be written exactly as it appears in a real file -
    including a self-closing one, which cannot carry the declarations
    itself.
    """
    holder = etree.fromstring(f"<holder {NAMESPACES}>{xml}</holder>")
    return list(holder)


def fragment(xml):
    """Parse a single piece of body XML."""
    return parse_all(xml)[0]


# --- reading the text a person would actually see ----------------------------

def test_a_tab_becomes_a_space():
    """
    A heading is written as the number, a tab, then the title. The tab
    element holds no characters, so reading the text naively gives
    "1Introduction" - and the typed number would then go unnoticed, because
    a typed number is only recognized when something separates it from the
    title.
    """
    heading = fragment('<text:h text:outline-level="1">1<text:tab/>Introduction</text:h>')
    assert odt._visible_text(heading) == "1 Introduction"


def test_alternative_text_of_an_image_is_not_read():
    """
    The description inside an image frame is written for screen readers and
    never appears in the running text. Letting it in would give every
    standalone figure a paragraph full of text, which is the signal that
    marks an image as pasted into a line.
    """
    paragraph = fragment(
        '<text:p>'
        '<draw:frame text:anchor-type="as-char">'
        '<draw:image xlink:href="Pictures/one.png" '
        'xmlns:xlink="http://www.w3.org/1999/xlink"/>'
        '<svg:desc>A flowchart of records</svg:desc>'
        '</draw:frame>'
        '</text:p>')
    assert odt._visible_text(paragraph) == ""


def test_ordinary_text_is_read_normally():
    paragraph = fragment('<text:p>Student dropout is a <text:span>persistent'
                         '</text:span> challenge.</text:p>')
    assert odt._visible_text(paragraph) == \
        "Student dropout is a persistent challenge."


# --- deciding whether a heading is really numbered ----------------------------

STYLE_NAME = "{urn:oasis:names:tc:opendocument:xmlns:style:1.0}name"


def styles_from(*definitions):
    """A {name: style} lookup built from style definitions written as XML."""
    return {style.get(STYLE_NAME): style
            for style in parse_all("".join(definitions))}


def test_an_empty_list_style_name_switches_numbering_off():
    """
    This is the signal that decides it, and it is easy to misread: the
    attribute is present but EMPTY, which means the numbering the outline
    style would otherwise give this level is switched off for this style.
    """
    styles = styles_from(
        '<style:style style:name="Heading_20_1" style:list-style-name=""/>')
    assert odt._resolve_numbering("Heading_20_1", "1", styles, {"1": True}) is False


def test_numbering_applies_when_no_style_objects():
    """With nothing switching it off, the document's outline numbering wins."""
    styles = styles_from('<style:style style:name="Heading_20_1"/>')
    assert odt._resolve_numbering("Heading_20_1", "1", styles, {"1": True}) is True


def test_the_style_chain_is_followed():
    """
    A heading usually uses an automatic style created by the editor, whose
    parent is the real heading style. The answer lives on the parent, so
    stopping at the first style would get every such heading wrong.
    """
    styles = styles_from(
        '<style:style style:name="P6" style:parent-style-name="Heading_20_1"/>',
        '<style:style style:name="Heading_20_1" style:list-style-name=""/>')
    assert odt._resolve_numbering("P6", "1", styles, {"1": True}) is False


def test_an_outline_level_without_numbering_is_not_numbered():
    """A level whose outline style names no number format is unnumbered."""
    styles = styles_from('<style:style style:name="Heading_20_1"/>')
    assert odt._resolve_numbering("Heading_20_1", "1", styles, {"1": False}) is False


def test_a_style_chain_that_points_at_itself_does_not_loop():
    """A guard, the same one the Word extractor keeps for its style chain."""
    styles = styles_from(
        '<style:style style:name="Loop" style:parent-style-name="Loop"/>')
    assert odt._resolve_numbering("Loop", "1", styles, {"1": True}) is True


# --- the format plugs into the registry --------------------------------------

def test_odt_is_registered_for_its_extension():
    """Importing the module is what makes .odt files checkable."""
    import extractors

    assert ".odt" in extractors.supported_extensions()
    assert extractors.extractor_for("submission.odt") is not None
