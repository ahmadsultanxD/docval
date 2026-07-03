# docval

Structural validation of scientific documents for automated assessment.

Part of the CodeOcean Autograder project, Assessing Office Documents.
Master's research project, TU Ilmenau.

## What it checks

A document is judged on whether it uses real document structure - real
heading styles with correct nesting and automatic numbering, a table of
contents that is genuinely linked to the headings, required sections
present as real headings, real list formatting, correctly placed real
captions, and equations in the equation format - not on text typed to
look like structure.

## Usage

```
python docval.py path/to/document.docx
python docval.py path/to/document.docx --json
python docval.py path/to/document.docx --config course.json
```

Exit code 0 means the document passed every enabled check; 1 means issues
were found. `--json` prints the machine-readable form.

`--config` points at a JSON file that overrides the built-in policy: which
sections are required (with per-language synonyms), which caption and list
labels each language uses, and which checks are active. See `DEFAULTS` in
[config.py](config.py) for the complete shape; a file only needs the keys
it wants to change.

## Architecture

- **extractor.py** - reads a .docx and produces the shared representation:
  an ordered list of typed blocks (`model.py`) plus document-wide facts.
  One extractor per format; OpenOffice and LaTeX extractors are planned.
- **rules.py** - the checks, written once against the representation,
  shared by every format.
- **reporter.py** - the readable and the JSON output forms.
- **config.py** - everything that varies per course, as data.
- **docval.py** - the command that ties it together.
