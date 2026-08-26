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
python docval.py path/to/document.docx --structure structure.json --styles styles.json
```

The format is chosen by the file extension: Word (.docx), OpenDocument
(.odt) and LaTeX (.tex). Exit code 0 means the document passed every
enabled check; 1 means issues were found; 2 means the file could not be
checked. `--json` prints the machine-readable form.

## The property files

Everything specific to one course lives in two JSON property files, edited
without touching code (see [examples/](examples/) for commented templates):

- **Structure** (`--structure`) - WHAT the document must contain: the
  required sections with their per-language synonyms, in the order they
  are expected to appear. A section out of order is an issue. An empty
  sections list means no section requirements at all - any sections are
  fine, as long as they are properly structured.
- **Styles** (`--styles`) - HOW the document must be formatted: the
  heading hierarchy rules (starting level, no skipped levels), caption
  positions and labels per language, custom list labels (like "RQ" for
  research questions), and which checks are active.

Both files are optional - built-in defaults apply - and a file only needs
the entries it wants to change.

## Tests

```bash
python -m pytest
```

The suite in [tests/](tests/) covers four things: the labeled sample
ladders (each version must report exactly the issues its label says), the
real-world LaTeX constructs the authored samples never contained (chapters,
parts, multi-file documents, run-in labels, code listings), each rule on
its own against documents built by hand, and the loading of the property
files.

## Architecture

- **extractors.py** - the plug-in socket: the `DocumentExtractor`
  interface every format implements, and the registry that finds the
  right extractor for a file. Supporting a new format means writing one
  new extractor module and adding one import line in `docval.py`.
- **word_extractor.py / odt_extractor.py / latex_extractor.py** - one
  extractor per format, each producing the same shared representation: an
  ordered list of typed blocks (`model.py`) plus document-wide facts.
- **patterns.py** - recognizes structure that was typed rather than built
  ("Table 1:" captions, "RQ1:" lists, keyboard formulas); faked structure
  looks the same in every format, so these are shared by all extractors.
- **rules.py** - the checks, written once against the representation,
  shared by every format.
- **reporter.py** - the readable and the JSON output forms.
- **config.py** - loads the Structure and Styles property files over the
  built-in defaults.
- **docval.py** - the command that ties it together.
=======
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
python docval.py path/to/document.docx --structure structure.json --styles styles.json
```

The format is chosen by the file extension; Word (.docx) and LaTeX (.tex)
are supported, OpenOffice (.odt) is planned. Exit code 0 means the document
passed every enabled check; 1 means issues were found; 2 means the file
could not be checked. `--json` prints the machine-readable form.

## The property files

Everything specific to one course lives in two JSON property files, edited
without touching code (see [examples/](examples/) for commented templates):

- **Structure** (`--structure`) - WHAT the document must contain: the
  required sections with their per-language synonyms, in the order they
  are expected to appear. A section out of order is an issue. An empty
  sections list means no section requirements at all - any sections are
  fine, as long as they are properly structured.
- **Styles** (`--styles`) - HOW the document must be formatted: the
  heading hierarchy rules (starting level, no skipped levels), caption
  positions and labels per language, custom list labels (like "RQ" for
  research questions), and which checks are active.

Both files are optional - built-in defaults apply - and a file only needs
the entries it wants to change.

## Architecture

- **extractors.py** - the plug-in socket: the `DocumentExtractor`
  interface every format implements, and the registry that finds the
  right extractor for a file. Supporting a new format means writing one
  new extractor module and adding one import line in `docval.py`.
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
- **config.py** - loads the Structure and Styles property files over the
  built-in defaults.
- **docval.py** - the command that ties it together.