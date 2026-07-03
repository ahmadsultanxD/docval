"""
docval.py - the entry point: one command that reads a file and prints the result.

Everything built so far meets here, in the order of the architecture:
extract the document into the representation, run the checks over it,
report what they found. Usage:

    python docval.py path/to/document.docx
    python docval.py path/to/document.docx --json
    python docval.py path/to/document.docx --config course.json

The exit code is part of the interface, because automation (and eventually
CodeOcean) reads it before reading any output: 0 means the document passed
every enabled check, 1 means issues were found.
"""

import argparse
import sys

import config as configuration
from extractor import extract
from reporter import report_json, report_text
from rules import enabled_checks, run_checks


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="docval",
        description="Check the structural quality of a scientific document.")
    parser.add_argument("file",
                        help="the document to check (.docx)")
    parser.add_argument("--json", action="store_true",
                        help="print the machine-readable JSON form")
    parser.add_argument("--config",
                        help="path to a JSON file overriding the built-in "
                             "configuration (required sections, labels, "
                             "active checks)")
    args = parser.parse_args(argv)

    # Windows consoles do not always speak UTF-8; a caption preview with a
    # special character should degrade, not crash the run.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    active_config = configuration.load(args.config)
    model = extract(args.file, active_config)
    issues = run_checks(model, active_config)

    if args.json:
        print(report_json(args.file, issues, enabled_checks(active_config)))
    else:
        print(report_text(args.file, issues))

    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
