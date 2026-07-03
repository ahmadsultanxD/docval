"""
extractor.py - Step 3 (complete): turn a real document into filled-in Blocks.

This is where the reader and the model meet. The reader walked the body but saw
only flat text. The model can hold real identity but was filled by hand. Here we
open the real document, walk it in order, and for each element work out its true
type: headings (with level and whether they are really auto-numbered), tables,
figures, captions (table or figure, real or typed), and plain paragraphs. We
also record two document-wide facts: whether a real table of contents exists,
and the heading bookmarks it can link to.

Two parts of this are genuinely tricky, and both were proven on the sample:

  1) Numbering lives on the STYLE, not the paragraph.
     In the sample, the heading paragraphs carry no numbering of their own.
     The "1", "2", "3" come from the Heading 1 style, which points at a
     numbering definition. So to know if a heading is auto-numbered, we cannot
     just look at the paragraph. If the paragraph has nothing, we follow its
     style, and that style's parent, and so on, looking for the numbering.

  2) Heading detection must ignore the style NAME.
     The sample's heading style is named "berschrift1" (German), not
     "Heading 1". Matching on the English name would fail on a German document.
     Instead we read the OUTLINE LEVEL, a number 0 to 8 that Word stores to mark
     a paragraph as a heading of that depth. It is the same in every language.
     A heading at outline level 0 is level 1, outline level 1 is level 2, etc.
"""

import re
import sys
import docx
from docx.oxml.ns import qn
from lxml import etree

from config import DEFAULTS
from model import Block, DocModel


# Word stores real equations in their own namespace (OMML, Office Math Markup
# Language), separate from the ordinary text namespace. qn() only knows the
# common prefixes, so we spell this one out.
M_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"


def _compile_patterns(config):
    """
    Build the language-dependent lookups from the config: which words label
    which caption kind, and what a typed list marker looks like.

    Word stores a hidden "SEQ" field in real captions ("SEQ Table"), and the
    label is localized, so the config lists the accepted words per kind. The
    same words recognize typed captions ("Table 1 ..." with no field behind
    it). For lists, the typed marker is a bullet character, a number like
    "1." or "1)", a lowercase letter like "a)" (lowercase only, because a
    capital with a period would match initials in a references list, "A.
    Smith"), or one of the configured labels ("RQ1:") - in a real list that
    label comes from the numbering definition in word/numbering.xml and
    never appears in the text nodes; typed as ordinary text it marks a fake.
    """
    seq_labels = {}
    for kind, labels in config["caption_labels"].items():
        for label in labels:
            seq_labels[label.lower()] = kind
    faked_caption_re = re.compile(
        r"^\s*(%s)\s+\d+" % "|".join(seq_labels), re.I)
    typed_list_re = re.compile(
        r"^\s*(?:[-•*·▪–]\s+|\d+[.)]\s+|[a-z][.)]\s+|(?:%s)\d+[.:)]?\s*)"
        % "|".join(config["list_labels"]))
    return seq_labels, faked_caption_re, typed_list_re


# A typed equation: an "=" with a math operator somewhere around it, in text
# that has no real math object behind it. Deliberately conservative - "=" on
# its own appears in ordinary prose ("p = 0.05"), so we also require one of
# the distinctly mathematical symbols. The hyphen is left out of the operator
# class on purpose: it is everywhere in prose. This heuristic is UNVERIFIED
# against a labeled sample; the set contains no faked equation yet.
TYPED_EQUATION_RE = re.compile(
    r"=[^=]*[+*/·∙×^√∑∫≤≥≈]|[+*/·∙×^√∑∫≤≥≈][^=]*="
)


# --- small helpers for reading the XML ---------------------------------------

def _get_style_id(p_el):
    """Return the style id applied to a paragraph, or None if it has none."""
    ppr = p_el.find(qn("w:pPr"))
    if ppr is None:
        return None
    p_style = ppr.find(qn("w:pStyle"))
    return p_style.get(qn("w:val")) if p_style is not None else None


def _style_chain(style_obj):
    """
    Yield a style and the styles it is based on, one after another.

    A style can be 'based on' a parent style and inherit its settings. To find
    inherited numbering or outline level, we walk this chain. The 'seen' set
    guards against a style accidentally pointing back at itself.
    """
    seen = set()
    current = style_obj
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.base_style


def _resolve_outline(p_el, style_obj):
    """
    Find the outline level (0..8) for this paragraph, or None if it is not a
    heading. Look on the paragraph first, then walk up the style chain.
    """
    # 1) Is it set directly on the paragraph?
    ppr = p_el.find(qn("w:pPr"))
    if ppr is not None:
        outline = ppr.find(qn("w:outlineLvl"))
        if outline is not None:
            return int(outline.get(qn("w:val")))
    # 2) Otherwise, is it set on the style, or a style it is based on?
    for style in _style_chain(style_obj):
        s_ppr = style.element.find(qn("w:pPr"))
        if s_ppr is not None:
            s_outline = s_ppr.find(qn("w:outlineLvl"))
            if s_outline is not None:
                return int(s_outline.get(qn("w:val")))
    return None


def _resolve_numbering(p_el, style_obj):
    """
    Return True if this paragraph is really auto-numbered.

    Same idea as the outline level: check the paragraph, then the style chain.
    One special case: a numbering id of "0" is Word's way of switching numbering
    OFF, so we treat that as not numbered.
    """
    def read_num_id(ppr):
        if ppr is None:
            return None
        num_pr = ppr.find(qn("w:numPr"))
        if num_pr is None:
            return None
        num_id = num_pr.find(qn("w:numId"))
        return num_id.get(qn("w:val")) if num_id is not None else None

    # 1) Numbering set directly on the paragraph (this also wins if it is "0").
    p_ppr = p_el.find(qn("w:pPr"))
    direct = read_num_id(p_ppr)
    if direct is not None:
        return direct != "0"
    # 2) Otherwise look on the style chain.
    for style in _style_chain(style_obj):
        s_num_id = read_num_id(style.element.find(qn("w:pPr")))
        if s_num_id is not None:
            return s_num_id != "0"
    return False


def _has_drawing(p_el):
    """True if the paragraph contains an image (a drawing)."""
    return p_el.find(".//" + qn("w:drawing")) is not None


def _has_math(p_el):
    """True if the paragraph contains a real equation (an OMML math object)."""
    return p_el.find(".//" + M_NS + "oMath") is not None


def _footnote_paragraphs(document):
    """
    Yield the paragraphs of every footnote in the document.

    Footnotes do not live in the document body at all: they are a separate
    XML part, word/footnotes.xml, that the body only points at. The samples
    put their equations in footnotes, so skipping this part would mean never
    seeing them. python-docx does not model footnotes, but it does give us
    the raw part through the document's relationships, and its XML uses the
    same w:p paragraphs we already know how to read.
    """
    for rel in document.part.rels.values():
        if rel.reltype.endswith("/footnotes"):
            root = etree.fromstring(rel.target_part.blob)
            for p_el in root.iter(qn("w:p")):
                yield p_el


def _seq_label(p_el):
    """
    Return the SEQ label of a real caption ('Table' or 'Figure'), or None.

    A real Word caption is auto-numbered by a hidden SEQ field. We read the
    field's instruction text and pull out the word after 'SEQ'. If there is no
    SEQ field, this is not a real caption.
    """
    parts = []
    for instr in p_el.findall(".//" + qn("w:instrText")):
        if instr.text:
            parts.append(instr.text)
    for fld in p_el.findall(".//" + qn("w:fldSimple")):
        value = fld.get(qn("w:instr"))
        if value:
            parts.append(value)
    match = re.search(r"SEQ\s+(\w+)", " ".join(parts))
    return match.group(1) if match else None


# --- the extractor -----------------------------------------------------------

def extract(path, config=None):
    """
    Open a .docx and return a DocModel of typed Blocks.

    The config supplies the language-dependent tables (caption labels, list
    labels); without one, the built-in defaults apply.
    """
    if config is None:
        config = DEFAULTS
    seq_labels, faked_caption_re, typed_list_re = _compile_patterns(config)

    document = docx.Document(path)

    # Build a lookup from style id to the style object, so we can follow the
    # style chain when resolving numbering and outline level.
    styles_by_id = {s.style_id: s for s in document.styles if s.style_id}

    model = DocModel()
    body = document.element.body
    index = 0

    for child in body:
        # A table is its own kind of block. We do not look inside it here.
        if child.tag == qn("w:tbl"):
            model.blocks.append(Block(index=index, type="table"))
            index += 1
            continue

        # We only handle paragraphs beyond this point.
        if child.tag != qn("w:p"):
            continue

        p_el = child
        text = "".join(node.text or "" for node in p_el.iter(qn("w:t")))
        style_id = _get_style_id(p_el)
        style_obj = styles_by_id.get(style_id)
        style_name = style_obj.name if style_obj is not None else None

        outline = _resolve_outline(p_el, style_obj)
        numbered = _resolve_numbering(p_el, style_obj)

        # While we are on this paragraph, collect three document-wide facts.
        # (a) Heading bookmarks: a heading listed in the table of contents
        #     carries a "_Toc" bookmark that the TOC's entry links to. We only
        #     collect them from real headings: cross-references create their
        #     own bookmarks (named "_Ref", sitting on captions in the samples),
        #     and collecting from every paragraph would count those too - the
        #     miscount the plan warned about.
        if outline is not None and 0 <= outline <= 8:
            for bookmark in p_el.findall(".//" + qn("w:bookmarkStart")):
                name = bookmark.get(qn("w:name")) or ""
                if name.startswith("_Toc"):
                    model.heading_bookmarks.append(name)
        # (b) TOC anchors: each entry of a real table of contents is a
        #     hyperlink whose anchor names the heading bookmark it jumps to.
        #     Collecting these is what lets a rule verify the TOC is really
        #     LINKED to the headings, not merely present.
        for hyperlink in p_el.findall(".//" + qn("w:hyperlink")):
            anchor = hyperlink.get(qn("w:anchor")) or ""
            if anchor.startswith("_Toc"):
                model.toc_anchors.append(anchor)
        # (c) The TOC field itself: a real table of contents is a field whose
        #     instruction contains "TOC". If we see it, the document has one.
        for instr in p_el.findall(".//" + qn("w:instrText")):
            if instr.text and "TOC" in instr.text:
                model.toc_present = True
        for fld in p_el.findall(".//" + qn("w:fldSimple")):
            if "TOC" in (fld.get(qn("w:instr")) or ""):
                model.toc_present = True

        # Decide the block's type. Order matters: figure, then caption (real or
        # typed), then heading, otherwise a plain paragraph.
        block = Block(index=index, type="paragraph", text=text,
                      style_name=style_name, numbered=numbered)

        seq = _seq_label(p_el)

        if _has_math(p_el):
            # A real equation, wherever it sits in the paragraph. This must
            # come before the drawing test so that a paragraph mixing text
            # and math is recognized as an equation, not prose.
            block.type = "equation"
            block.real = True
        elif _has_drawing(p_el):
            block.type = "figure"
            # An image inside a line of text, rather than standing in its own
            # empty paragraph, is how a pasted equation or symbol usually
            # arrives. We cannot see inside the pixels, so we only record the
            # placement here and let a rule decide what to make of it.
            block.inline = bool(text.strip())
        elif seq is not None:
            # A real caption: it has a SEQ field. Record which kind.
            block.type = "caption"
            block.real = True
            block.kind = seq_labels.get(seq.lower())
        elif faked_caption_re.match(text or ""):
            # Looks like a caption ("Table 1 ...") but has no SEQ field: typed.
            block.type = "caption"
            block.real = False
            label = faked_caption_re.match(text).group(1).lower()
            block.kind = seq_labels.get(label)
        elif outline is not None and 0 <= outline <= 8:
            block.type = "heading"
            block.level = outline + 1
        elif numbered:
            # A real list item: the paragraph carries real numbering (its own
            # or through its style) but no outline level, so it is not a
            # heading. This must come AFTER the heading test: v1 taught us
            # that a document can fake numbered headings by using a numbered
            # list style, and those must not be mistaken for headings - but
            # as list items their formatting is genuine, so real is True.
            block.type = "list_item"
            block.real = True
        elif typed_list_re.match(text or ""):
            # Looks like a list item ("- ...", "1. ...", "RQ1: ...") but has
            # no real numbering behind it: the marker is typed text.
            block.type = "list_item"
            block.real = False
        elif TYPED_EQUATION_RE.search(text or ""):
            # Looks like an equation but has no math object behind it: the
            # formula was typed as ordinary text.
            block.type = "equation"
            block.real = False

        model.blocks.append(block)
        index += 1

    # Finally, the footnotes. They are not part of the body's reading order,
    # so we do not push their prose through the full classification - a
    # footnote is not where headings, captions, or lists belong. The one
    # structural thing that legitimately lives there is an equation, so that
    # is the only thing we look for. Appending these blocks after the body
    # keeps the body's order intact for the position-based caption checks.
    for p_el in _footnote_paragraphs(document):
        text = "".join(node.text or "" for node in p_el.iter(qn("w:t")))
        if _has_math(p_el):
            model.blocks.append(Block(index=index, type="equation",
                                      text=text, real=True))
            index += 1
        elif TYPED_EQUATION_RE.search(text):
            model.blocks.append(Block(index=index, type="equation",
                                      text=text, real=False))
            index += 1

    return model


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "Sample Documents/Word/Assignment_v8.docx"
    print(f"Extracting: {path}\n")

    model = extract(path)
    print(f"Produced {len(model.blocks)} blocks.")
    print(f"TOC present: {model.toc_present}   heading bookmarks: "
          f"{len(model.heading_bookmarks)}   TOC anchors: {len(model.toc_anchors)}\n")
    for b in model.blocks:
        lvl = f"L{b.level}" if b.level else "  "
        num = "[num]" if b.numbered else "     "
        extra = ""
        if b.type == "caption":
            extra = f"({b.kind}, {'real' if b.real else 'typed'})"
        preview = b.text.strip()
        if len(preview) > 45:
            preview = preview[:45] + "..."
        print(f"{b.index:3}  {b.type:10} {lvl:3} {num}  {preview} {extra}")


if __name__ == "__main__":
    main()