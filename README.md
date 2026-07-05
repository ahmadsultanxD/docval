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
python docval.py path/to/document.tex
python docval.py path/to/document.docx --json
python docval.py path/to/document.docx --config course.json
```

The format is chosen by the file extension; Word (.docx) and LaTeX (.tex)
are supported, OpenOffice (.odt) is planned. Exit code 0 means the document
passed every enabled check; 1 means issues were found; 2 means the file
could not be checked. `--json` prints the machine-readable form.

`--config` points at a JSON file that overrides the built-in policy: which
sections are required (with per-language synonyms), which caption and list
labels each language uses, and which checks are active. See `DEFAULTS` in
[config.py](config.py) for the complete shape; a file only needs the keys
it wants to change.

## Architecture

- **word_extractor.py / latex_extractor.py** - one extractor per format,
  each producing the same shared representation: an ordered list of typed
  blocks (`model.py`) plus document-wide facts. An OpenOffice extractor
  is planned.
- **patterns.py** - recognizes structure that was typed rather than built
  ("Table 1:" captions, "RQ1:" lists, keyboard formulas); faked structure
  looks the same in every format, so these are shared by all extractors.
- **rules.py** - the checks, written once against the representation,
  shared by every format.
- **reporter.py** - the readable and the JSON output forms.
- **config.py** - everything that varies per course, as data.
- **docval.py** - the command that ties it together.
