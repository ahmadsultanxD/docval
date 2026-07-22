"""
latex_extractor.py - the second extractor: LaTeX source into the same Blocks.

Read a .tex file and produce exactly the representation the Word extractor produces,
so that rules.py and reporter.py run on it unchanged.

LaTeX makes some things easier than Word and some things harder:

  1) Real structure is explicit in the source. A \\section IS a real heading,
     and it is auto-numbered by default - the faked forms are the starred
     \\section* (unnumbered, skipped by the table of contents), a lowered
     secnumdepth counter (numbering off), or no sectioning command at all,
     just bold text. So "is this heading numbered" is not a hunt through
     style chains like in Word; it is: not starred, and within secnumdepth.

  2) There are no paragraph marks. LaTeX separates paragraphs by blank
     lines, and TexSoup hands us an interleaved stream of text pieces and
     command nodes. The extractor rebuilds paragraphs from that stream:
     text accumulates in a buffer, a blank line or a block-level command
     flushes it as one Block.

  3) The table of contents is generated FROM the sectioning commands, so a
     \\tableofcontents is linked to the headings by construction. The
     representation records that fact by giving every TOC-eligible heading
     (unstarred, within tocdepth) the same synthetic name in both
     heading_bookmarks and toc_anchors. A document whose headings are all
     starred genuinely produces an empty table of contents - and then the
     anchors stay empty and the linked check reports it, which is honest.

Typed (faked) structure - "Table 1:" captions, "RQ1:" lists, keyboard
formulas - looks the same in every format, so those patterns come from
patterns.py, shared with the Word extractor.
"""

import re
import sys
from TexSoup import TexSoup

from config import DEFAULT_STYLES
from extractors import DocumentExtractor, register
from model import Block, DocModel
from patterns import TYPED_EQUATION_RE, compile_patterns


# Sectioning commands and the heading level they map to. Article-class
# depths; \chapter (report/book classes) is left out until a sample needs
# it, because mapping it correctly shifts every other level down by one.
SECTION_LEVELS = {
    "section": 1,
    "subsection": 2,
    "subsubsection": 3,
    "paragraph": 4,
    "subparagraph": 5,
}

# Math that stands on its own line becomes an equation block of its own;
# math inside a sentence marks the surrounding paragraph as an equation,
# the same way an inline OMML object does in Word. TexSoup names \(...\)
# and $...$ 'math' and '$'.
INLINE_MATH = {"math", "$"}
DISPLAY_MATH = {"$$", "displaymath", "equation", "equation*",
                "align", "align*", "gather", "gather*", "multline", "eqnarray"}

LIST_ENVS = {"itemize", "enumerate", "description"}
TABULAR_ENVS = {"tabular", "tabularx", "longtable", "array"}

# Commands whose content is invisible in the running text: flattening them
# into the paragraph would leak internal names ("tab:picoc") into the text.
SKIP = {"label", "centering", "newpage", "clearpage", "pagebreak",
        "noindent", "vspace", "hspace", "maketitle", "index"}

# LaTeX's own defaults for the article class: sections down to
# \subsubsection are numbered and listed in the table of contents.
DEFAULT_SECNUMDEPTH = 3
DEFAULT_TOCDEPTH = 3

# LaTeX separates paragraphs with blank lines, but TexSoup collapses every
# newline run to a single "\n" - after parsing, a paragraph break and an
# ordinary line wrap look identical. So before parsing, every blank-line
# run in the source is replaced by an explicit marker command. TexSoup
# tokenizes the marker as a node, the walker flushes the paragraph when it
# meets one, and no information is lost.
PAR_MARKER = "docvalpar"
_PARAGRAPH_BREAK_SRC = re.compile(r"\n[ \t]*\n(?:[ \t]*\n)*")

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


def _flatten(node):
    """
    All the visible text inside a node, in order, as one string.

    A command's argument can nest another command inside it - an acronym
    or citation macro used INSIDE a caption or section title, say
    ("\\caption{The \\ac{CNN} architecture}"). Most TexSoup nodes have a
    ".text" property that already walks through everything nested and
    returns just the visible text, but a few of TexSoup's internal node
    types do not expose that shortcut. For those, we fall back to walking
    ".contents" ourselves, one piece at a time, recursing until only
    plain text is left.
    """
    if isinstance(node, str):
        return node
    if hasattr(node, "text"):
        return "".join(_flatten(piece) for piece in node.text)
    if hasattr(node, "contents"):
        return "".join(_flatten(piece) for piece in node.contents)
    return str(node)


def _arg_text(node):
    """The text of a command's last argument - a section or caption title."""
    if not node.args:
        return ""
    return _flatten(node.args[-1])


def extract(path, styles=None):
    """
    Read a .tex source file and return a DocModel of typed Blocks.

    The styles supply the same language tables as for Word; without them,
    the built-in defaults apply.
    """
    if styles is None:
        styles = DEFAULT_STYLES
    seq_labels, faked_caption_re, typed_list_re = compile_patterns(styles)

    with open(path, encoding="utf-8") as f:
        source = f.read()
    source = _PARAGRAPH_BREAK_SRC.sub("\n\\\\%s\n" % PAR_MARKER, source)
    soup = TexSoup(source)

    # Preamble fact: has the author turned section numbering off (or down)?
    secnumdepth = DEFAULT_SECNUMDEPTH
    for counter in soup.find_all("setcounter"):
        args = [str(a)[1:-1] for a in counter.args]  # strip the braces
        if len(args) == 2 and args[0] == "secnumdepth":
            secnumdepth = int(args[1])

    model = DocModel()
    headings = []     # (block, starred), for the TOC synthesis at the end
    footnotes = []    # footnote nodes, handled after the body like in Word

    # The paragraph being rebuilt from the stream: its text pieces, and
    # whether an image or inline math was seen inside it.
    buffer = []
    has_image = False
    has_math = False
    index = 0

    def emit(block):
        nonlocal index
        block.index = index
        model.blocks.append(block)
        index += 1

    def flush():
        """Close the current paragraph and decide what kind of Block it is.

        The decision order mirrors the Word extractor exactly: math first,
        then image, then the typed imitations, then plain paragraph."""
        nonlocal buffer, has_image, has_math
        text = re.sub(r"\s+", " ", "".join(buffer)).strip()
        buffer, image, math = [], has_image, has_math
        has_image = has_math = False

        if math:
            emit(Block(index=0, type="equation", text=text, real=True))
        elif image:
            # An image with text around it sits inside a line - the pasted
            # form; alone in its paragraph it is a standalone figure.
            emit(Block(index=0, type="figure", text=text,
                       inline=bool(text)))
        elif not text:
            return
        elif faked_caption_re.match(text):
            label = faked_caption_re.match(text).group(1).lower()
            emit(Block(index=0, type="caption", text=text,
                       real=False, kind=seq_labels.get(label)))
        elif typed_list_re.match(text):
            emit(Block(index=0, type="list_item", text=text, real=False))
        elif TYPED_EQUATION_RE.search(text):
            emit(Block(index=0, type="equation", text=text, real=False))
        else:
            emit(Block(index=0, type="paragraph", text=text))

    def feed_text(piece):
        """Add running text to the paragraph, flushing at blank lines."""
        nonlocal buffer
        parts = _PARAGRAPH_BREAK.split(piece)
        buffer.append(parts[0])
        for part in parts[1:]:
            flush()
            buffer.append(part)

    document = soup.find("document")
    for item in (document.contents if document else []):
        if isinstance(item, str):
            feed_text(item)
            continue

        name = item.name

        if name == PAR_MARKER:
            flush()

        elif name.rstrip("*") in SECTION_LEVELS:
            flush()
            starred = name.endswith("*")
            level = SECTION_LEVELS[name.rstrip("*")]
            # Numbering in LaTeX is the default, not an achievement: real,
            # unstarred sectioning within secnumdepth numbers itself.
            block = Block(index=0, type="heading", text=_arg_text(item).strip(),
                          level=level,
                          numbered=(not starred and level <= secnumdepth))
            emit(block)
            headings.append((block, starred))

        elif name == "tableofcontents":
            flush()
            model.toc_present = True

        elif name in LIST_ENVS:
            flush()
            for entry in item.find_all("item"):
                emit(Block(index=0, type="list_item",
                           text=_flatten(entry).strip(), real=True))

        elif name == "table":
            flush()
            # Walk the environment in order, so the caption block lands
            # above or below the table block exactly as it does in source.
            for child in item.contents:
                if isinstance(child, str):
                    continue
                if child.name == "caption":
                    emit(Block(index=0, type="caption", kind="table",
                               real=True, text=_arg_text(child).strip()))
                elif child.name in TABULAR_ENVS:
                    emit(Block(index=0, type="table"))

        elif name == "figure":
            flush()
            for child in item.contents:
                if isinstance(child, str):
                    continue
                if child.name == "caption":
                    emit(Block(index=0, type="caption", kind="figure",
                               real=True, text=_arg_text(child).strip()))
                elif child.name == "includegraphics":
                    emit(Block(index=0, type="figure"))

        elif name in DISPLAY_MATH:
            flush()
            emit(Block(index=0, type="equation",
                       text=re.sub(r"\s+", " ", _flatten(item)).strip(),
                       real=True))

        elif name in INLINE_MATH:
            has_math = True
            buffer.append(_flatten(item))

        elif name == "footnote":
            # Footnotes are out of the reading order; like in Word, they are
            # handled after the body, and their text stays out of the
            # paragraph they hang on.
            footnotes.append(item)

        elif name == "includegraphics":
            has_image = True

        elif name in SKIP:
            pass

        else:
            # An unknown command in running text (\textbf, \emph, \cite...):
            # keep its visible text, drop the command itself.
            buffer.append(_flatten(item))

    flush()

    # The footnotes, appended after the body like in the Word extractor:
    # the one structural thing that legitimately lives there is an equation.
    for footnote in footnotes:
        text = re.sub(r"\s+", " ", _flatten(footnote)).strip()
        has_note_math = any(child.name in INLINE_MATH | DISPLAY_MATH
                            for child in footnote.contents
                            if not isinstance(child, str))
        if has_note_math:
            emit(Block(index=0, type="equation", text=text, real=True))
        elif TYPED_EQUATION_RE.search(text):
            emit(Block(index=0, type="equation", text=text, real=False))

    # The table of contents is generated from the sectioning commands, so
    # its entries are linked by construction - to the headings the TOC
    # actually lists, which starred sections are not. Both sides get the
    # same synthetic names; if every heading is starred, the anchors stay
    # empty and check_toc_linked reports the (genuinely empty) TOC.
    if model.toc_present:
        for position, (block, starred) in enumerate(headings):
            if not starred and block.level <= DEFAULT_TOCDEPTH:
                name = f"sec{position}"
                model.heading_bookmarks.append(name)
                model.toc_anchors.append(name)

    return model


class LatexExtractor(DocumentExtractor):
    """The LaTeX format's plug into the extractor registry."""

    extensions = (".tex",)

    def extract(self, path, styles=None):
        return extract(path, styles)


# Importing this module is what makes the format available.
register(LatexExtractor())


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "Sample Documents/LaTeX/Assignment_v8.tex"
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
        if b.type == "equation":
            extra = f"({'real' if b.real else 'typed'})"
        preview = b.text.strip()
        if len(preview) > 45:
            preview = preview[:45] + "..."
        print(f"{b.index:3}  {b.type:10} {lvl:3} {num}  {preview} {extra}")


if __name__ == "__main__":
    main()
