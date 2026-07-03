"""
reporter.py - Step 6: turn the issue list into output someone can use.

The checks produce Issue objects; two audiences need to read them. A person
wants a short, scannable list saying what is wrong and where. A machine (the
CodeOcean integration, a test script) wants the same facts in a stable JSON
shape it can parse without guessing. Both forms are direct serializations of
what the checks found - the reporter adds no judgment of its own.

The JSON shape is deliberately boring: the file that was checked, which
checks ran (so "no issues" can be told apart from "the check was switched
off"), a passed flag, and the issues with their stable check ids. Once the
CodeOcean integration consumes this, the shape is published and changing it
is a breaking change.
"""

import json
from dataclasses import asdict


def report_text(path, issues):
    """The human-readable form: one line per issue, with its place."""
    lines = [f"docval: {path}"]
    if not issues:
        lines.append("No structural issues found.")
        return "\n".join(lines)

    lines.append(f"{len(issues)} issue(s) found.")
    lines.append("")
    for issue in issues:
        where = (f"block {issue.block_index}"
                 if issue.block_index is not None else "document")
        lines.append(f"  [{issue.check}]  ({where})  {issue.message}")
    return "\n".join(lines)


def report_json(path, issues, checks_run):
    """The machine-readable form, as a JSON string."""
    return json.dumps({
        "file": str(path),
        "checks_run": checks_run,
        "passed": not issues,
        "issues": [asdict(issue) for issue in issues],
    }, indent=2, ensure_ascii=False)
