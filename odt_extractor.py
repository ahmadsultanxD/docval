"""
odt_extractor.py - the third extractor: OpenDocument text into the same Blocks.

An .odt file, like a .docx, is a zip of XML. The body lives in content.xml
and the named styles in styles.xml, and we read both with lxml directly -
no extra library, the same way the Word extractor reaches footnotes.xml.

OpenDocument is the friendliest of the three formats to read, because most
of what we need has an element of its own rather than having to be inferred:

  1) A heading IS an element. <text:h text:outline-level="2"> says both that
     the paragraph is a heading and how deep it sits. There is no style name
     to match and therefore no language problem, which is the same reason
     the Word extractor reads outline levels instead of style names.

  2) A real caption carries a <text:sequence> field, the direct counterpart
     of Word's SEQ field, and it names its own kind ("Table", "Figure").

Two things do need care, and both were confirmed against the samples rather
than taken from the specification:

  1) Numbering is switched off by an EMPTY string. The outline style defines
     the numbering for each level, and a heading's paragraph style opts out
     by carrying style:list-style-name="". That empty value is the signal,
     which is the same trick Word plays with a numbering id of "0". The
     style chain has to be followed too, because a heading often uses an
     automatic style whose parent is the real heading style.

  2) Some text in the file is not text. A <text:tab/> produces no characters
     of its own, so a heading written as "1<tab>Introduction" would read as
     "1Introduction" and its typed number would go unnoticed; tabs become
     spaces. In the other direction, the <svg:desc> inside an image frame is
     alternative text for screen readers, and letting it into the paragraph
     would make every standalone figure look like an inline one.
"""

import sys
import zipfile

from lxml import etree

from config import DEFAULT_STYLES
from extractors import DocumentExtractor, register
from model import Block, DocModel
from patterns import TYPED_EQUATION_RE, compile_patterns


# The OpenDocument namespaces we read. Spelled out once here, because an
# element is only found if its namespace matches exactly.
OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
DRAW = "{urn:oasis:names:tc:opendocument:xmlns:drawing:1.0}"
STYLE = "{urn:oasis:names:tc:opendocument:xmlns:style:1.0}"
SVG = "{urn:oasis:names:tc:opendocument:xmlns:svg-compatible-draw:1.0}"
XLINK = "{http://www.w3.org/1999/xlink}"

# Elements that stand for a space but contain no characters of their own.
WHITESPACE_ELEMENTS = {TEXT + "tab", TEXT + "s", TEXT + "line-break"}

# Alternative text for an image: written for screen readers, never shown in
# the running text, so it must not be read as part of the paragraph.
DESCRIPTION_ELEMENTS = {"desc", "title"}


def _visible_text(element):
    """
    The text a reader would see in this element, in order.

    Walking the tree ourselves rather than using itertext() is what lets us
    turn a tab into a space and leave an image's alternative text out.
    """
    parts = []

    def walk(node):
        for child in node:
            tag = child.tag
            if not isinstance(tag, str):
                continue  # a comment or processing instruction
            local = etree.QName(child).localname
            if tag in WHITESPACE_ELEMENTS:
                parts.append(" ")
            elif local in DESCRIPTION_ELEMENTS:
                pass  # alternative text, not running text
            else:
                if child.text:
                    parts.append(child.text)
                walk(child)
            if child.tail:
                parts.append(child.tail)

    if element.text:
        parts.append(element.text)
    walk(element)
    return " ".join("".join(parts).split())


def _styles_by_name(content_root, styles_root):
    """
    Every style in the document, by name.

    Styles live in two places: the named ones an author picks from the
    sidebar are in styles.xml, and the automatic ones the editor creates
    when something is tweaked are in content.xml. A heading commonly uses
    an automatic style whose parent is the real heading style, so both
    parts have to be here for the chain to be followed.
    """
    found = {}
    for root in (styles_root, content_root):
        for style in root.iter(STYLE + "style"):
            name = style.get(STYLE + "name")
            if name and name not in found:
                found[name] = style
    return found


def _outline_numbering(styles_root):
    """
    Which heading levels the document's outline style numbers.

    Returns {level: True/False}. A level is numbered when its
    style:num-format names a format ("1", "A", "I"); an empty format means
    the outline is not numbered at that level.
    """
    numbered = {}
    for level_style in styles_root.iter(TEXT + "outline-level-style"):
        level = level_style.get(TEXT + "level")
        numbered[level] = bool(level_style.get(STYLE + "num-format"))
    return numbered


def _resolve_numbering(style_name, level, styles_by_name, outline_numbering):
    """
    True if this heading is really numbered by the document.

    The paragraph's own style has the final word: a style:list-style-name of
    "" switches numbering off for it, and a non-empty one names a list style
    that provides numbering. If no style in the chain says anything, the
    document's outline numbering for that level applies.
    """
    seen = set()
    while style_name and style_name not in seen:
        seen.add(style_name)
        style = styles_by_name.get(style_name)
        if style is None:
            break
        list_style = style.get(STYLE + "list-style-name")
        if list_style is not None:
            return bool(list_style)
        style_name = style.get(STYLE + "parent-style-name")
    return outline_numbering.get(level, False)


def _sequence_name(paragraph):
    """
    The kind a real caption names for itself, or None.

    A caption made by the editor numbers itself with a <text:sequence>
    field, and the field's name is the sequence it counts: "Table",
    "Figure", or the localized word for one of them.
    """
    sequence = paragraph.find(".//" + TEXT + "sequence")
    return sequence.get(TEXT + "name") if sequence is not None else None


def _image_frame(paragraph):
    """The frame of the image in this paragraph, or None if it has none."""
    for frame in paragraph.iter(DRAW + "frame"):
        if frame.find(DRAW + "image") is not None:
            return frame
    return None


def _has_formula(paragraph):
    """
    True if the paragraph holds a real formula.

    A formula made with the equation editor is embedded as its own little
    document and referenced by a <draw:object>, which is the OpenDocument
    counterpart of Word's OMML math object.
    """
    return paragraph.find(".//" + DRAW + "object") is not None


def extract(path, styles=None):
    """
    Open an .odt and return a DocModel of typed Blocks.

    The styles supply the language-dependent tables (caption labels, list
    labels); without them, the built-in defaults apply.
    """
    if styles is None:
        styles = DEFAULT_STYLES
    seq_labels, faked_caption_re, typed_list_re = compile_patterns(styles)

    with zipfile.ZipFile(path) as archive:
        content_root = etree.fromstring(archive.read("content.xml"))
        styles_root = etree.fromstring(archive.read("styles.xml"))

    styles_by_name = _styles_by_name(content_root, styles_root)
    outline_numbering = _outline_numbering(styles_root)

    model = DocModel()
    body = content_root.find(".//" + OFFICE + "text")
    index = 0

    def emit(block):
        nonlocal index
        block.index = index
        model.blocks.append(block)
        index += 1

    for element in (body if body is not None else []):
        tag = element.tag
        if not isinstance(tag, str):
            continue

        # A real table of contents. Its own entries are links naming the
        # heading bookmarks they jump to, which is what lets a rule check
        # that the contents are LINKED and not merely present. The index's
        # own paragraphs are not document content, so they are not walked.
        if tag == TEXT + "table-of-content":
            model.toc_present = True
            for link in element.iter(TEXT + "a"):
                target = link.get(XLINK + "href") or ""
                if target.startswith("#"):
                    model.toc_anchors.append(target[1:])
            continue

        if tag == TABLE + "table":
            emit(Block(index=0, type="table"))
            continue

        # A real list: every item in it is genuinely formatted as one.
        if tag == TEXT + "list":
            for item in element.iter(TEXT + "list-item"):
                emit(Block(index=0, type="list_item", real=True,
                           text=_visible_text(item)))
            continue

        if tag == TEXT + "h":
            level = element.get(TEXT + "outline-level")
            style_name = element.get(TEXT + "style-name")
            # A heading listed in the table of contents carries a bookmark
            # that the contents link to. Collected only from headings, so
            # that bookmarks made for cross-references are not counted.
            for bookmark in element.iter(TEXT + "bookmark-start"):
                name = bookmark.get(TEXT + "name") or ""
                if name.startswith("_Toc"):
                    model.heading_bookmarks.append(name)
            emit(Block(
                index=0, type="heading", text=_visible_text(element),
                style_name=style_name,
                level=int(level) if level and level.isdigit() else 1,
                numbered=_resolve_numbering(style_name, level,
                                            styles_by_name, outline_numbering),
            ))
            continue

        if tag != TEXT + "p":
            continue  # something we do not model, such as a page break

        text = _visible_text(element)
        block = Block(index=0, type="paragraph", text=text,
                      style_name=element.get(TEXT + "style-name"))

        sequence = _sequence_name(element)
        frame = _image_frame(element)

        # The order mirrors the other extractors: formula, then image, then
        # a real caption, then the typed imitations, then plain prose.
        if _has_formula(element):
            block.type = "equation"
            block.real = True
        elif frame is not None:
            block.type = "figure"
            # A pasted picture of an equation sits INSIDE a line of text.
            # Two things have to hold for that, and the anchor type alone is
            # not enough: nearly every image in these documents is anchored
            # "as-char", including figures that stand alone on their own
            # paragraph with a caption underneath. So the anchor has to be
            # as-char AND the paragraph has to carry text of its own, which
            # is the same signal the Word extractor uses.
            block.inline = (frame.get(TEXT + "anchor-type") == "as-char"
                            and bool(text))
        elif sequence is not None:
            block.type = "caption"
            block.real = True
            block.kind = seq_labels.get(sequence.lower())
        elif faked_caption_re.match(text):
            block.type = "caption"
            block.real = False
            label = faked_caption_re.match(text).group(1).lower()
            block.kind = seq_labels.get(label)
        elif typed_list_re.match(text):
            block.type = "list_item"
            block.real = False
        elif TYPED_EQUATION_RE.search(text):
            block.type = "equation"
            block.real = False

        emit(block)

    return model


class OdtExtractor(DocumentExtractor):
    """The OpenDocument format's plug into the extractor registry."""

    extensions = (".odt",)

    def extract(self, path, styles=None):
        return extract(path, styles)


# Importing this module is what makes the format available.
register(OdtExtractor())


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else \
        "Sample Documents/LibreOffice/Assignment_v8.odt"
    print(f"Extracting: {path}\n")

    model = extract(path)
    print(f"Produced {len(model.blocks)} blocks.")
    print(f"TOC present: {model.toc_present}   heading bookmarks: "
          f"{len(model.heading_bookmarks)}   TOC anchors: {len(model.toc_anchors)}\n")
    for b in model.blocks:
        level = f"L{b.level}" if b.level else "  "
        numbered = "[num]" if b.numbered else "     "
        extra = ""
        if b.type == "caption":
            extra = f"({b.kind}, {'real' if b.real else 'typed'})"
        if b.type == "equation":
            extra = f"({'real' if b.real else 'typed'})"
        if b.type == "figure" and b.inline:
            extra = "(inline)"
        preview = b.text.strip()
        if len(preview) > 45:
            preview = preview[:45] + "..."
        print(f"{b.index:3}  {b.type:10} {level:3} {numbered}  {preview} {extra}")


if __name__ == "__main__":
    main()
