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
     Because being unnumbered is legitimate in LaTeX rather than a missing
     structure, the only numbering FAULT is a number typed into the title.

  1b) The document class decides what the levels mean. An article starts at
     \\section; a report or a book starts at \\chapter and pushes everything
     else down one place, while numbering one level less deeply. Reading a
     report with the article table would misjudge every heading in it, so
     the extractor works out which kind of document it has first.

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

import os
import re
import sys
from TexSoup import TexSoup

from config import DEFAULT_STYLES
from extractors import DocumentExtractor, register
from model import Block, DocModel
from patterns import TYPED_EQUATION_RE, compile_patterns


# The sectioning commands, from the widest division to the narrowest. Which
# of them a document actually uses varies: \chapter exists only in the
# report and book classes, and \part is rare outside long theses and books.
# The outline level of a heading is simply its place in this list once the
# commands the document does not use are removed - so a \section is level 1
# in an article, level 2 in a report, and level 3 in a report with parts.
# Getting this wrong misreads every heading level in the document.
SECTION_ORDER = ["part", "chapter", "section", "subsection", "subsubsection"]

# Classes that provide \chapter. Thesis templates often define their own
# class on top of book or report, so the class name alone is not enough -
# the extractor also looks for a \chapter actually being used.
CHAPTER_CLASSES = {
    "report", "book", "memoir", "scrreprt", "scrbook", "thesis", "extreport",
    "extbook", "mwrep", "mwbk",
}

# LaTeX's OWN internal level numbers, which are what \setcounter{secnumdepth}
# and \setcounter{tocdepth} are measured against. They are NOT the outline
# levels above: in a report, \chapter is LaTeX level 0 while its outline
# level is 1. Comparing the wrong one against secnumdepth would decide
# numbering incorrectly for every chapter-based document. Only \part and
# \chapter differ between the classes; everything below them agrees.
LATEX_LEVELS = {
    "part": 0, "section": 1, "subsection": 2, "subsubsection": 3,
    "paragraph": 4, "subparagraph": 5,
}
LATEX_LEVELS_WITH_CHAPTERS = dict(LATEX_LEVELS, part=-1, chapter=0)


def _outline_levels(uses_part, uses_chapters):
    """
    The outline level of each sectioning command this document uses.

    Built by dropping the commands the document does not have and numbering
    what is left from 1, so the four possible shapes (article, article with
    parts, report, report with parts) all come out of one rule instead of
    four hand-written tables.
    """
    available = {"part": uses_part, "chapter": uses_chapters}
    commands = [name for name in SECTION_ORDER if available.get(name, True)]
    return {name: level for level, name in enumerate(commands, start=1)}


# \paragraph and \subparagraph are NOT outline headings, even though LaTeX
# lists them among the sectioning commands. They are run-in labels: the title
# is set in bold at the START of a paragraph and the body text continues on
# the same line ("\paragraph{Credit Assignment.} When multiple agents..."),
# which is how they read on the page. LaTeX itself treats them that way - by
# default it neither numbers them nor puts them in the table of contents.
# Reading them as heading levels 4 and 5 made every ordinary
# "\subsection then \paragraph" pair look like a skipped heading level, so
# their text simply flows into the paragraph they open.
RUN_IN_HEADINGS = {"paragraph", "subparagraph"}

# Commands whose arguments are never visible text: a file path, a length, a
# citation key, a label, a package name. This matters because TexSoup's own
# ".text" returns those arguments anyway, so flattening any stretch of a
# document that contains one splices them into the running text - which is
# how "\includegraphics[height=2cm]{pics/logo-thi.jpg}" on a title page
# turned into the text "height=2cmpics/logo-thi.jpg" and was then reported
# as a typed equation, because it contains an "=" and a "/".
INVISIBLE_ARGS = {
    "includegraphics", "label", "ref", "pageref", "eqref", "autoref",
    "nameref", "cite", "citep", "citet", "nocite",
    "bibliography", "bibliographystyle",
    "usepackage", "documentclass",
    "newcommand", "renewcommand", "providecommand", "DeclareOldFontCommand",
    "definecolor", "setcounter", "addtocounter", "setlength", "addtolength",
    "hspace", "vspace", "rule", "usetikzlibrary", "geometry", "hypersetup",
    "graphicspath", "captionsetup", "pagestyle", "thispagestyle",
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

# Environments holding code or output rather than prose. Their contents are
# not document structure and must not be read as any: a listing containing
# "rate = alpha * decay" is a line of code, not a formula typed instead of
# an equation. They are stepped over entirely.
CODE_ENVS = {"verbatim", "verbatim*", "lstlisting", "minted", "Verbatim",
             "alltt", "listing", "code"}

# Commands whose content is invisible in the running text: flattening them
# into the paragraph would leak internal names ("tab:picoc") into the text.
SKIP = {"label", "centering", "newpage", "clearpage", "pagebreak",
        "noindent", "vspace", "hspace", "maketitle", "index"}

# LaTeX's own defaults, as internal level numbers. An article numbers and
# lists everything down to \subsubsection (level 3); a report or a book
# stops one level higher (level 2), which means \subsubsection is unnumbered
# there by default - not a fault, just how the class is set up.
ARTICLE_DEPTH = 3
CHAPTER_CLASS_DEPTH = 2

# LaTeX separates paragraphs with blank lines, but TexSoup collapses every
# newline run to a single "\n" - after parsing, a paragraph break and an
# ordinary line wrap look identical. So before parsing, every blank-line
# run in the source is replaced by an explicit marker command. TexSoup
# tokenizes the marker as a node, the walker flushes the paragraph when it
# meets one, and no information is lost.
PAR_MARKER = "docvalpar"
_PARAGRAPH_BREAK_SRC = re.compile(r"\n[ \t]*\n(?:[ \t]*\n)*")

# \input{chapters/intro} and \include{chapters/intro}, matched in the source
# text before parsing. The lookahead keeps \includegraphics out of it: that
# command continues with letters where these two reach their brace.
_INCLUDE_RE = re.compile(r"\\(input|include)(?![a-zA-Z])\s*\{([^}]*)\}")

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


def _flatten(node):
    """
    All the visible text inside a node, in order, as one string.

    We walk the node's own contents rather than using TexSoup's ".text"
    shortcut, because ".text" returns the arguments of every command it
    meets - including the ones that are not text at all, like the file path
    in \\includegraphics or the length in \\vspace. Walking ourselves lets
    us drop those (INVISIBLE_ARGS) and keep everything else, at any depth:
    a citation or acronym macro nested inside a caption or a section title
    is flattened to its visible text just as it would be typeset.
    """
    if isinstance(node, str):
        return node

    name = getattr(node, "name", None)
    if name in INVISIBLE_ARGS:
        return ""

    contents = getattr(node, "contents", None)
    if contents is not None:
        return "".join(_flatten(piece) for piece in contents)
    return str(node)


def _clean_text(text):
    """
    Tidy a stretch of extracted text into the one line it reads as.

    Two things happen. Runs of whitespace become single spaces, because a
    paragraph in the source is wrapped across many lines but is one piece of
    text on the page. And "~" becomes a space: in LaTeX it is a
    non-breaking space, written to keep a citation or a number attached to
    the word before it ("Section~\\ref{...}"), so leaving it as a tilde
    would put a stray character in the middle of a title.
    """
    return re.sub(r"\s+", " ", text.replace("~", " ")).strip()


def _arg_text(node):
    """The text of a command's last argument - a section or caption title."""
    if not node.args:
        return ""
    return _flatten(node.args[-1])


def _raw_args(node):
    """
    A command's arguments as plain strings, with their braces removed.

    Used for the preamble commands whose arguments are names and numbers
    rather than text - \\documentclass{article}, \\setcounter{tocdepth}{2} -
    which _flatten deliberately refuses to read.
    """
    return [str(arg)[1:-1] for arg in node.args]


def _uses_command(soup, name):
    """True if the document uses a command, in its plain or starred form."""
    return soup.find(name) is not None or soup.find(name + "*") is not None


def _uses_chapters(soup):
    """
    True if this document's headings start at \\chapter rather than \\section.

    Two signals, either of which is enough. The class name is the obvious
    one, but it is not reliable on its own: university thesis templates
    routinely define a class of their own on top of book or report, and we
    would not recognize the name. So we also look for a \\chapter actually
    being used, which is the document telling us directly.
    """
    declaration = soup.find("documentclass")
    if declaration is not None:
        args = _raw_args(declaration)
        if args and args[-1].strip().lower() in CHAPTER_CLASSES:
            return True
    return _uses_command(soup, "chapter")


def _expand_includes(source, base_dir, already_read):
    """
    Replace every \\input{...} and \\include{...} with the text of that file.

    Long documents are almost never one file: a thesis keeps each chapter in
    its own .tex and pulls them together from a short main file. Reading
    only the main file would find a document with no content at all, so the
    pieces are spliced in before anything is parsed. Doing it on the source
    text, rather than while walking, means the rest of the extractor never
    has to know that more than one file was involved - and the checks that
    look at the document as a whole, like which sectioning commands it uses,
    see the complete picture.

    A file that cannot be found is left out rather than treated as an error:
    a submission may well reference something the marker does not have, and
    the rest of the document is still worth checking. 'already_read' stops
    a file that includes itself from looping forever.
    """
    def read_included(match):
        name = match.group(2).strip()
        candidate = os.path.join(base_dir, name)
        if not os.path.splitext(candidate)[1]:
            candidate += ".tex"
        candidate = os.path.abspath(candidate)

        if candidate in already_read or not os.path.isfile(candidate):
            return ""
        already_read.add(candidate)

        with open(candidate, encoding="utf-8", errors="replace") as f:
            included = f.read()
        # The included file may pull in files of its own, relative to where
        # IT sits, so each one is expanded from its own directory.
        return _expand_includes(included, os.path.dirname(candidate),
                                already_read)

    return _INCLUDE_RE.sub(read_included, source)


def _counter_value(soup, counter_name, default):
    """The value a \\setcounter in the preamble gives a counter, or default."""
    for node in soup.find_all("setcounter"):
        args = _raw_args(node)
        if len(args) == 2 and args[0].strip() == counter_name:
            try:
                return int(args[1])
            except ValueError:
                pass  # a counter set to something we cannot read: keep default
    return default


def extract(path, styles=None):
    """
    Read a .tex source file and return a DocModel of typed Blocks.

    The styles supply the same language tables as for Word; without them,
    the built-in defaults apply.
    """
    if styles is None:
        styles = DEFAULT_STYLES
    seq_labels, faked_caption_re, typed_list_re = compile_patterns(styles)

    with open(path, encoding="utf-8", errors="replace") as f:
        source = f.read()
    # Splice in any files the document is built from, before anything else
    # looks at it, so a thesis kept in one file per chapter reads the same
    # as a thesis kept in one file.
    source = _expand_includes(source, os.path.dirname(os.path.abspath(path)),
                              {os.path.abspath(path)})
    source = _PARAGRAPH_BREAK_SRC.sub("\n\\\\%s\n" % PAR_MARKER, source)
    soup = TexSoup(source)

    # Which kind of document is this? A report or a book starts its outline
    # at \chapter, and a long one may group those into \part, each pushing
    # the levels below it down one place. The depth defaults follow from the
    # class in the same way.
    chapter_based = _uses_chapters(soup)
    section_levels = _outline_levels(_uses_command(soup, "part"), chapter_based)
    latex_levels = LATEX_LEVELS_WITH_CHAPTERS if chapter_based else LATEX_LEVELS
    class_depth = CHAPTER_CLASS_DEPTH if chapter_based else ARTICLE_DEPTH

    # Preamble facts: has the author turned numbering, or the table of
    # contents, off or down from what the class does by default?
    secnumdepth = _counter_value(soup, "secnumdepth", class_depth)
    tocdepth = _counter_value(soup, "tocdepth", class_depth)

    model = DocModel()
    headings = []     # (block, starred), for the TOC synthesis at the end
    footnotes = []    # footnote nodes, handled after the body like in Word

    # The paragraph being rebuilt from the stream: its text pieces, and
    # whether an image, inline math, or a run-in label was seen inside it.
    buffer = []
    has_image = False
    has_math = False
    has_run_in = False
    index = 0

    def emit(block):
        nonlocal index
        block.index = index
        model.blocks.append(block)
        index += 1

    def flush():
        """Close the current paragraph and decide what kind of Block it is.

        The decision order mirrors the Word extractor exactly: math first,
        then image, then the typed imitations, then plain paragraph.

        One case is skipped on purpose. The "typed imitation" tests exist to
        catch text PRETENDING to be structure, but a paragraph opened by a
        run-in label already used a real LaTeX command to say what it is.
        Its title lands at the front of the text, so a label like
        "\\paragraph{RQ1: Scalability approaches.}" would otherwise look
        exactly like a typed "RQ1:" list marker - a discussion paragraph
        reported as a faked list."""
        nonlocal buffer, has_image, has_math, has_run_in
        text = _clean_text("".join(buffer))
        buffer, image, math = [], has_image, has_math
        run_in = has_run_in
        has_image = has_math = has_run_in = False

        if run_in and not (math or image):
            if text:
                emit(Block(index=0, type="paragraph", text=text))
            return

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

        elif name.rstrip("*") in RUN_IN_HEADINGS:
            # A run-in label, not an outline heading: its title opens the
            # paragraph, so it joins the running text rather than becoming
            # a heading block of its own. Remember that it was a real
            # command, so flush() does not mistake the label for typed text.
            has_run_in = True
            buffer.append(_flatten(item))

        elif name.rstrip("*") in section_levels:
            flush()
            command = name.rstrip("*")
            starred = name.endswith("*")
            level = section_levels[command]
            latex_level = latex_levels[command]
            # Numbering in LaTeX is the default, not an achievement: real,
            # unstarred sectioning within secnumdepth numbers itself. So an
            # unnumbered heading is not a missing-structure fault the way it
            # is in Word - the author either wrote \section* on purpose (an
            # Abstract, Acknowledgements, References) or used a level that
            # LaTeX itself leaves unnumbered (\paragraph, \subparagraph).
            # 'numbering_optional' tells the rule engine that, so it only
            # reports the real fault: a number typed into the title.
            block = Block(index=0, type="heading", text=_clean_text(_arg_text(item)),
                          level=level,
                          numbered=(not starred and latex_level <= secnumdepth),
                          numbering_optional=True)
            emit(block)
            headings.append((block, starred, latex_level))

        elif name == "tableofcontents":
            flush()
            model.toc_present = True

        elif name in LIST_ENVS:
            flush()
            for entry in item.find_all("item"):
                emit(Block(index=0, type="list_item",
                           text=_clean_text(_flatten(entry)), real=True))

        elif name in CODE_ENVS:
            # A listing is not prose: step over it so its code is never read
            # as a paragraph, a typed formula, or anything else structural.
            flush()

        elif name.rstrip("*") == "table":
            flush()
            # Walk the environment in order, so the caption block lands
            # above or below the table block exactly as it does in source.
            # The starred form (table*) is the same thing spanning both
            # columns of a two-column paper.
            for child in item.contents:
                if isinstance(child, str):
                    continue
                if child.name.rstrip("*") == "caption":
                    emit(Block(index=0, type="caption", kind="table",
                               real=True, text=_clean_text(_arg_text(child))))
                elif child.name.rstrip("*") in TABULAR_ENVS:
                    emit(Block(index=0, type="table"))

        elif name.rstrip("*") == "figure":
            flush()
            for child in item.contents:
                if isinstance(child, str):
                    continue
                if child.name.rstrip("*") == "caption":
                    emit(Block(index=0, type="caption", kind="figure",
                               real=True, text=_clean_text(_arg_text(child))))
                elif child.name == "includegraphics":
                    emit(Block(index=0, type="figure"))

        elif name in DISPLAY_MATH:
            flush()
            emit(Block(index=0, type="equation",
                       text=_clean_text(_flatten(item)),
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
        text = _clean_text(_flatten(footnote))
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
        for position, (block, starred, latex_level) in enumerate(headings):
            if not starred and latex_level <= tocdepth:
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
