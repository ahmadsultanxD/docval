"""
model.py - Step 2: the data shapes that hold a document's structure.

The reader gave us loose pairs of (kind, text). That is not enough. To check
structure, each element needs a proper identity: is it a real heading, and at
what level? Is its numbering automatic or just typed? If it is a caption, is it
for a table or a figure, and is it a real caption or typed text?

So we define one container, Block, that holds an element together with
everything we learn about it. A document then becomes an ordered list of these
Blocks, plus a few facts about the document as a whole (does it have a table of
contents, and which headings are bookmarked).

Nothing here parses a document. These are empty containers, ready to be filled
in the next step. We use Python's dataclasses, which are a short way to define a
class that mainly holds named fields.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Block:
    """
    One top-level element of the document, with its identity.

    Only a few fields apply to any given block. A heading uses 'level' and
    'numbered'; a caption uses 'kind' and 'real'; a plain paragraph uses
    almost none. Fields that do not apply simply stay at their default.
    """

    index: int                       # position in the document, 0, 1, 2, ...
    type: str                        # heading | paragraph | list_item | table | figure | caption | equation
    text: str = ""                   # the visible text, empty for a table or an image

    style_name: Optional[str] = None  # the Word style name, e.g. "heading 1"
    level: Optional[int] = None       # for a heading: 1, 2, 3, ...
    numbered: bool = False            # True if numbering is automatic (not typed)
    numbering_optional: bool = False  # for a heading: True when the format
                                      # numbers headings by itself, so being
                                      # unnumbered is a deliberate choice by
                                      # the author (LaTeX's \section*), not a
                                      # failure to use real structure

    kind: Optional[str] = None        # for a caption: "table" or "figure"
    real: Optional[bool] = None       # for a caption, list, or equation: real mechanism vs typed text
    inline: bool = False              # for a figure: pasted inside a line of text
                                      # rather than standing in its own paragraph


@dataclass
class DocModel:
    """
    A whole document as we will work with it: an ordered list of Blocks,
    plus a couple of document-wide facts the rules will need.
    """

    blocks: list = field(default_factory=list)   # the elements, in order
    toc_present: bool = False                     # is there a real table-of-contents field?
    heading_bookmarks: list = field(default_factory=list)  # names of "_Toc" bookmarks
                                                  # that sit ON heading paragraphs
    toc_anchors: list = field(default_factory=list)  # bookmark names the table of
                                                  # contents' hyperlink entries point AT


# A small demonstration so you can see the shapes in use and run this file
# on its own. This is throwaway: it builds two blocks by hand, with no real
# document involved, just to show what a filled-in Block looks like.
def _demo():
    model = DocModel()

    # A made-up heading block.
    model.blocks.append(Block(
        index=0, type="heading", text="Introduction",
        style_name="heading 1", level=1, numbered=True,
    ))

    # A made-up plain paragraph block.
    model.blocks.append(Block(
        index=1, type="paragraph", text="Student dropout represents a challenge...",
    ))

    print("Document has", len(model.blocks), "blocks.")
    print("TOC present:", model.toc_present)
    print()
    for b in model.blocks:
        print(f"  [{b.index}] {b.type:10} level={b.level} numbered={b.numbered}  {b.text[:40]}")


if __name__ == "__main__":
=======
"""
model.py - Step 2: the data shapes that hold a document's structure.

The reader gave us loose pairs of (kind, text). That is not enough. To check
structure, each element needs a proper identity: is it a real heading, and at
what level? Is its numbering automatic or just typed? If it is a caption, is it
for a table or a figure, and is it a real caption or typed text?

So we define one container, Block, that holds an element together with
everything we learn about it. A document then becomes an ordered list of these
Blocks, plus a few facts about the document as a whole (does it have a table of
contents, and which headings are bookmarked).

Nothing here parses a document. These are empty containers, ready to be filled
in the next step. We use Python's dataclasses, which are a short way to define a
class that mainly holds named fields.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Block:
    """
    One top-level element of the document, with its identity.

    Only a few fields apply to any given block. A heading uses 'level' and
    'numbered'; a caption uses 'kind' and 'real'; a plain paragraph uses
    almost none. Fields that do not apply simply stay at their default.
    """

    index: int                       # position in the document, 0, 1, 2, ...
    type: str                        # heading | paragraph | list_item | table | figure | caption | equation
    text: str = ""                   # the visible text, empty for a table or an image

    style_name: Optional[str] = None  # the Word style name, e.g. "heading 1"
    level: Optional[int] = None       # for a heading: 1, 2, 3, ...
    numbered: bool = False            # True if numbering is automatic (not typed)

    kind: Optional[str] = None        # for a caption: "table" or "figure"
    real: Optional[bool] = None       # for a caption, list, or equation: real mechanism vs typed text
    inline: bool = False              # for a figure: pasted inside a line of text
                                      # rather than standing in its own paragraph


@dataclass
class DocModel:
    """
    A whole document as we will work with it: an ordered list of Blocks,
    plus a couple of document-wide facts the rules will need.
    """

    blocks: list = field(default_factory=list)   # the elements, in order
    toc_present: bool = False                     # is there a real table-of-contents field?
    heading_bookmarks: list = field(default_factory=list)  # names of "_Toc" bookmarks
                                                  # that sit ON heading paragraphs
    toc_anchors: list = field(default_factory=list)  # bookmark names the table of
                                                  # contents' hyperlink entries point AT


# A small demonstration so you can see the shapes in use and run this file
# on its own. This is throwaway: it builds two blocks by hand, with no real
# document involved, just to show what a filled-in Block looks like.
def _demo():
    model = DocModel()

    # A made-up heading block.
    model.blocks.append(Block(
        index=0, type="heading", text="Introduction",
        style_name="heading 1", level=1, numbered=True,
    ))

    # A made-up plain paragraph block.
    model.blocks.append(Block(
        index=1, type="paragraph", text="Student dropout represents a challenge...",
    ))

    print("Document has", len(model.blocks), "blocks.")
    print("TOC present:", model.toc_present)
    print()
    for b in model.blocks:
        print(f"  [{b.index}] {b.type:10} level={b.level} numbered={b.numbered}  {b.text[:40]}")


if __name__ == "__main__":
    _demo()