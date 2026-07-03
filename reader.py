"""
reader.py - Step 1: open a .docx file and reach its raw building blocks.

A .docx file is really a ZIP archive of XML files. python-docx opens that
archive and parses the XML for us. The real text and structure live in the
document body, as an ordered sequence of elements: paragraphs (w:p) and
tables (w:tbl), one after another in reading order.

This file does not interpret anything yet. It only proves we can open the
document and walk its top-level elements. Understanding the order of those
elements is the foundation for everything later, because rules like
"caption above the table" depend on reading them in order.
"""

import sys
import docx
from docx.oxml.ns import qn


def read_document(path):
    #Open a .docx and return its python-docx Document object
    document = docx.Document(path)
    return document


def walk_body(document):
    """
    Go through the document body in order and report what each
    top-level element is: a paragraph or a table.

    We read the body's children directly, rather than using
    document.paragraphs, because that built-in list skips tables and
    loses the original order. Order matters to us, so we walk the
    raw element tree ourselves.
    """
    body = document.element.body
    items = []
    for child in body:
        if child.tag == qn("w:p"):
            # A paragraph. Pull its visible text by joining the text nodes.
            text = "".join(node.text or "" for node in child.iter(qn("w:t")))
            items.append(("paragraph", text))
        elif child.tag == qn("w:tbl"):
            # A table. We do not look inside it yet.
            items.append(("table", ""))
        # Anything else (for example section settings) is skipped for now.
    return items


def main():
    # Take the file path from the command line, or fall back to a default.
    path = sys.argv[1] if len(sys.argv) > 1 else "Assignment_v8.docx"
    print(f"Reading: {path}\n")

    document = read_document(path)
    items = walk_body(document)

    print(f"Found {len(items)} top-level elements in the body.\n")
    for i, (kind, text) in enumerate(items):
        # Show a short preview of each element so the output stays readable.
        preview = text.strip()
        if len(preview) > 60:
            preview = preview[:60] + "..."
        print(f"{i:3}  {kind:10}  {preview}")


if __name__ == "__main__":
    main()