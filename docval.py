"""
docval.py - the entry point: one command that reads a file and prints the result.

Everything built so far meets here, in the order of the architecture:
extract the document into the representation, run the checks over it,
report what they found. Usage:

    python docval.py path/to/document.docx
    python docval.py path/to/document.docx --json
    python docval.py path/to/document.docx --structure structure.json --styles styles.json

The exit code is part of the interface, because automation (and eventually
CodeOcean) reads it before reading any output: 0 means the document passed
every enabled check, 1 means issues were found, 2 means the file could not
be checked at all (unsupported format).
"""

import argparse
import sys

import config as configuration
import extractors
from reporter import report_json, report_text
from rules import enabled_checks, run_checks

# Importing a format's module is what registers it with the extractor
# registry. Supporting a new format means writing its module and adding
# one import line here - nothing else in the engine changes.
import word_extractor   # noqa: F401  (registers .docx)
import latex_extractor  # noqa: F401  (registers .tex)
import odt_extractor    # noqa: F401  (registers .odt)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="docval",
        description="Check the structural quality of a scientific document.")
    parser.add_argument("file",
                        help="the document to check (.docx or .tex)")
    parser.add_argument("--json", action="store_true",
                        help="print the machine-readable JSON form")
    parser.add_argument("--structure",
                        help="path to a Structure property file: WHAT the "
                             "document must contain (the sections, in "
                             "expected order; an empty list checks none)")
    parser.add_argument("--styles",
                        help="path to a Styles property file: HOW the "
                             "document must be formatted (heading rules, "
                             "caption positions and labels, list labels, "
                             "active checks)")
    args = parser.parse_args(argv)

    # Windows consoles do not always speak UTF-8; a caption preview with a
    # special character should degrade, not crash the run.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    extractor = extractors.extractor_for(args.file)
    if extractor is None:
        supported = ", ".join(extractors.supported_extensions())
        print(f"docval: unsupported file type for {args.file!r}; "
              f"supported: {supported}", file=sys.stderr)
        return 2

    structure = configuration.load_structure(args.structure)
    styles = configuration.load_styles(args.styles)

    model = extractor.extract(args.file, styles)
    issues = run_checks(model, structure, styles)

    if args.json:
        print(report_json(args.file, issues, enabled_checks(styles)))
    else:
        print(report_text(args.file, issues))

    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
