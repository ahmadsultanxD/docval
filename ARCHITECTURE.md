# docval — Architecture and Implementation

Structural validation of scientific documents for automated assessment.
Part of the CodeOcean Autograder project ("Assessing Office Documents"),
Master's research project, TU Ilmenau.

This document describes what the project does, how it is built, why it is
built that way, and what has been verified. It is written to be read on its
own, without the codebase at hand.

---

## 1. The problem

Students are told to build documents with *real* structure: heading styles,
automatic numbering, a generated table of contents, real lists, real
captions. Many instead type text that *looks* like structure — a bold line
standing in for a heading, digits typed in front of a title, a hand-written
list of contents that never updates.

Visually the two are near-identical. Structurally they are completely
different, and only the real one survives editing, generates a correct table
of contents, or works with a screen reader.

docval reads a document, works out which of the two it actually is, and
reports every place the structure is faked or misplaced.

**Supported formats:** Word (`.docx`), OpenDocument (`.odt`), LaTeX (`.tex`).

---

## 2. The central design idea

Supporting three formats must not mean writing the checks three times. So
the project has exactly one stable boundary in the middle:

```
  a file                TRANSLATE                 JUDGE              PRESENT
┌──────────┐   ┌───────────────────────┐   ┌────────────────┐   ┌─────────────┐
│  .docx   │──▶│  word_extractor.py    │──▶│                │   │             │
│  .odt    │──▶│  odt_extractor.py     │──▶│    rules.py    │──▶│ reporter.py │
│  .tex    │──▶│  latex_extractor.py   │──▶│  (11 checks)   │   │ text / JSON │
└──────────┘   └───────────────────────┘   └───────▲────────┘   └─────────────┘
                    all produce a                  │
                    model.DocModel        Structure + Styles
                                          property files
```

Everything **left** of the `DocModel` is format-specific.
Everything **right** of it is written once and shared.

This yields three independent axes of change, each with exactly one home:

| To add… | You touch |
|---|---|
| a new **format** | one new extractor module + one import line |
| a new **check** | one function in `rules.py` + one registry line |
| a new **course policy** | a JSON property file — no code at all |

---

## 3. The shared representation (`model.py`)

Two small dataclasses. This is the contract every extractor writes and every
check reads.

```python
@dataclass
class Block:
    index: int                        # position in the document, 0,1,2,...
    type: str                         # heading | paragraph | list_item |
                                      # table | figure | caption | equation
    text: str = ""

    style_name: str | None = None     # the format's own style name, if any
    level: int | None = None          # for a heading: 1, 2, 3, ...
    numbered: bool = False            # numbering is automatic, not typed
    numbering_optional: bool = False  # unnumbered is legitimate in this format

    kind: str | None = None           # for a caption: "table" or "figure"
    real: bool | None = None          # real mechanism vs typed imitation
    inline: bool = False              # for a figure: pasted inside a line

@dataclass
class DocModel:
    blocks: list                      # the elements, in reading order
    toc_present: bool = False         # a real table-of-contents field exists
    heading_bookmarks: list           # bookmark names sitting ON headings
    toc_anchors: list                 # names the TOC's entries point AT
```

Three things this design gets right, each learned from a real failure:

- **`real`** separates "a caption exists" from "a caption mechanism exists".
  A typed `"Table 1: ..."` produces a `caption` block with `real=False`.
- **`heading_bookmarks` vs `toc_anchors`** are kept apart so a rule can
  check the TOC is genuinely *linked*, not merely present. An earlier
  single-list version also counted cross-reference bookmarks and miscounted.
- **`numbering_optional`** lets a format declare "unnumbered is a choice
  here". It is the one piece of format knowledge the rules consult, and the
  extractor sets it — see §6.

Blocks are stored in **reading order**, which is what makes position-based
rules ("a table's caption is directly above it") possible.

---

## 4. The plugin socket (`extractors.py`)

The engine never names a format. Formats register themselves.

```python
class DocumentExtractor(ABC):
    extensions = ()                       # e.g. (".docx",)

    @abstractmethod
    def extract(self, path, styles=None): # -> DocModel
        ...

def register(extractor):        # called once, at the bottom of each module
def extractor_for(path):        # registry lookup by file extension
def supported_extensions():     # for error messages
```

Registration happens as an **import side effect**: `docval.py` imports each
extractor module, and the `register(...)` call at the bottom of that module
runs. That is why the imports carry `# noqa: F401` — a linter would
otherwise flag them as unused.

**Adding OpenOffice took exactly three steps**, and this is the intended cost
of any future format:

1. Write `odt_extractor.py` with a class inheriting `DocumentExtractor`.
2. Call `register(OdtExtractor())` at the bottom of that file.
3. Add `import odt_extractor` to `docval.py`.

`rules.py`, `reporter.py`, and `config.py` were not touched.

---

## 5. The eleven checks (`rules.py`)

Each check is a plain function with the same signature, returning a list of
`Issue`s (empty means the document passes):

```python
def check_something(model: DocModel, structure, styles) -> list[Issue]
```

```python
@dataclass
class Issue:
    check: str            # stable id, e.g. "heading-hierarchy"
    message: str          # one human sentence
    block_index: int|None # where, or None if document-wide
    text: str = ""        # short preview of the offending block
```

The `check` id is **stable and published** — the property files and the JSON
output key on it, so it must not change even if the function is renamed.

Checks in run order:

| id | What it requires |
|---|---|
| `heading-hierarchy` | Real heading styles, correctly nested, no skipped level |
| `heading-numbering` | Numbering is automatic, not typed digits |
| `toc-present` | A real table-of-contents field exists |
| `toc-linked` | Its entries resolve to real heading bookmarks |
| `required-sections` | The configured sections exist as real headings |
| `section-order` | They appear in the configured order |
| `list-formatting` | Lists use real list formatting, not typed markers |
| `table-caption` | Every table has a real caption directly above |
| `figure-caption` | Every figure has a real caption directly below |
| `equation-format` | Equations use the real equation format |
| `inline-image` | No uncaptioned image pasted inside a line of text |

The first eight are the original plan. `equation-format` and `inline-image`
were added when the samples turned out to contain a *pasted picture* of an
equation. `section-order` came from a later requirement.

### Design decisions worth knowing

**An empty heading list is itself a finding.** A fully faked document
produces *zero* heading blocks, so walking the headings would find nothing
wrong and wrongly pass. `check_heading_hierarchy` reports the absence
directly.

**Checks defer to each other rather than double-report.** `toc-linked` stays
silent when there is no TOC at all (that is `toc-present`'s finding);
`section-order` ignores a missing section (that is `required-sections`');
`figure-caption` skips inline images (that is `inline-image`'s).

**Nothing is skipped to be kind.** A document with no real headings fails
every required-section check as well as the hierarchy check. Each is real
information for grading.

**Both sides of a name comparison are normalized** — lowercased, trimmed,
and a typed leading number stripped — so a document with typed heading
numbers fails only the *numbering* check, not also the *sections* check.

---

## 6. The one place format knowledge reaches the rules

`heading-numbering` is the single check whose meaning differs by format, and
the difference is carried by data, not by an `if` on the format:

- **Word / OpenDocument:** numbering must be switched on. A heading without
  it has not been given real structure → **reported**.
- **LaTeX:** numbering is the default. An unnumbered heading means the author
  deliberately wrote `\section*` (an Abstract, an Acknowledgements section)
  or used a level LaTeX leaves unnumbered → **not reported**.

The LaTeX extractor sets `numbering_optional=True` on its headings; the check
then reports only the fault that is a fault everywhere: **a number typed into
the title**.

---

## 7. Configuration: two property files (`config.py`)

Everything that varies per course is data an instructor edits. Nothing about
policy lives in code.

**Structure — WHAT the document must contain:**

```json
{
  "sections": [
    {"name": "Introduction", "accept": ["introduction", "einleitung"]},
    {"name": "Methodology"}
  ]
}
```

- Sections are checked **in the order listed**; one found earlier than a
  section listed before it is a `section-order` issue.
- `accept` is optional — a bare `{"name": "Introduction"}` is accepted under
  its own name. It exists only to add synonyms (e.g. a German translation).
- **An empty `sections` list switches all section checking off**: any
  sections are fine, while the style rules keep applying in full.

**Styles — HOW the document must be formatted:**

```json
{
  "headings":  {"first_level": 1, "max_deeper_step": 1},
  "captions":  {"table_position": "above", "figure_position": "below",
                "labels": {"table": ["table", "tabelle"],
                           "figure": ["figure", "abbildung"]}},
  "lists":     {"labels": ["RQ"]},
  "checks":    {"toc-present": false}
}
```

- `headings` parameterizes the hierarchy rule.
- `captions.labels` are the localized words identifying a caption's kind —
  they also catch *typed* captions.
- `lists.labels` names custom labelled sequences ("RQ1:" for research
  questions).
- `checks` switches individual checks off by id; anything absent is enabled.

**Loader behaviour:** built-in defaults mean the tool runs with zero setup;
a file overrides only the keys it names, merging **one level deep** inside a
group; keys starting with `_` are treated as comments; an unknown key raises
loudly, so a typo like `"cheks"` cannot silently disable nothing.

Commented, copy-ready templates live in `examples/`.

Verified: all three formats respond identically to every setting.

---

## 8. Typed-structure detection (`patterns.py`)

Real structure looks different in every format. **Faked structure looks the
same everywhere**, because it is just text imitating the real thing. So the
patterns that recognize it are shared by all extractors:

- typed captions — `"Table 1: ..."` with no caption field behind it
- typed list markers — bullets, `1.`, `a)`, or a configured label like `RQ1:`
- typed equations — an `=` near a mathematical operator, in text with no
  equation object behind it

Two deliberate exclusions in the equation pattern, both from false positives
found on real documents: the **hyphen** (everywhere in prose) and the
**forward slash** (everywhere in file paths, URLs and dates, often with an
`=` nearby).

> The typed-equation pattern remains **unverified against a labeled sample** —
> no sample document contains a keyboard-typed equation.

---

## 9. The three extractors

All three walk their format in reading order and emit the same blocks. What
differs is the evidence each format offers.

### 9.1 Word (`word_extractor.py`)

A `.docx` is a zip of XML, read with `python-docx` plus `lxml`.

- **Headings** are found by **outline level** (`w:outlineLvl`, 0–8), not by
  style name. The samples' heading style is the German `"Überschrift1"`, so
  matching `"Heading 1"` would fail. Outline level is language-independent.
- **Numbering lives on the STYLE, not the paragraph.** The digits come from
  the Heading style pointing at a numbering definition, so the extractor
  walks the paragraph → its style → that style's parent, until it finds a
  numbering id. A numbering id of `"0"` means numbering explicitly **off**.
- **Captions** carry a hidden `SEQ` field naming the sequence
  (`SEQ Table` / `SEQ Figure`); no SEQ field means a typed caption.
- **Equations** are OMML `m:oMath` objects, in their own namespace.
- **Footnotes** live in a separate part (`word/footnotes.xml`) that
  python-docx does not model; reached through the document relationships.
  Only equations are read from there.
- **TOC** is a field whose instruction contains `TOC`; heading bookmarks are
  `_Toc…` names collected **only from real headings**, so cross-reference
  bookmarks (`_Ref…`) are not miscounted.

### 9.2 OpenDocument (`odt_extractor.py`)

A `.odt` is a zip of XML, read with `zipfile` + `lxml` — **no new
dependency**. Body in `content.xml`, named styles in `styles.xml`.

The friendliest format to read: most facts have a dedicated element.

- **Headings** are `<text:h text:outline-level="2">` — the element states
  both that it is a heading and how deep it sits. No style-name matching, so
  no language problem.
- **Numbering** mirrors Word's logic in ODF clothing: the outline style
  defines it via `style:num-format`, and a paragraph style opts **out** with
  `style:list-style-name=""` — an *empty string* meaning "off", the direct
  analogue of Word's `numId="0"`. The style chain must be walked, because
  headings often use an automatic style (`P6`) whose parent is the real one.
- **Captions** carry `<text:sequence text:name="Table">` — the counterpart of
  Word's SEQ field, and with the same label words.
- **TOC** is `<text:table-of-content>` whose entries are
  `<text:a xlink:href="#_Toc…">`, with matching `_Toc` bookmarks on the
  headings — mechanically identical to Word.
- **Equations** are `<draw:object>` referencing an embedded formula.

Three traps, all found empirically:

1. `<text:tab/>` produces **no characters**, so `1<tab>Introduction` reads as
   `"1Introduction"` — and the typed-number pattern needs a separator after
   the digit, so the fault would be **silently missed**. Tabs become spaces.
2. `<svg:desc>` inside an image frame is **screen-reader alt text**. Letting
   it into the paragraph makes every standalone figure look inline.
3. `anchor-type="as-char"` does **not** mean "pasted inside a line" — nearly
   every image carries it. Inline requires as-char **and** the paragraph
   carrying text of its own.

### 9.3 LaTeX (`latex_extractor.py`)

Plain text, parsed with **TexSoup**. Structure is explicit in the source,
but the source is far more varied than the other two.

- **Outline levels are computed, not fixed.** `\part`, `\chapter`, `\section`,
  `\subsection`, `\subsubsection` form an ordered list; the commands the
  document does not use are dropped and the rest numbered from 1. One rule
  covers article, report, book, with or without parts. Using the wrong table
  misreads every heading in the document.
- **The document class is detected two ways**: from `\documentclass`, *and*
  from whether `\chapter` is actually used — because thesis templates
  routinely define their own class on top of `book`.
- **`secnumdepth`/`tocdepth` are compared against LaTeX's OWN internal level
  numbers**, which are not the outline levels (in a report `\chapter` is
  LaTeX level 0 but outline level 1). Class-dependent defaults: 3 for
  article, 2 for report/book.
- **`\paragraph` and `\subparagraph` are NOT outline headings.** They are
  run-in labels: the title is set bold and the body continues on the same
  line, and LaTeX neither numbers them nor lists them. Their text flows into
  the paragraph they open.
- **Multi-file documents**: `\input` and `\include` are expanded **before
  parsing**, so a thesis kept one file per chapter reads as one document —
  and the "which commands does this document use" detection sees everything.
  Missing files are skipped; self-inclusion cannot loop.
- **Paragraph reconstruction**: LaTeX has no paragraph marks, and TexSoup
  collapses newline runs, so a blank line and a line wrap become
  indistinguishable. The extractor replaces every blank-line run in the raw
  source with a marker command *before* parsing.
- **Text flattening is hand-rolled**, because TexSoup's `.text` returns the
  *arguments* of every command as if they were visible text. ~30 commands
  whose arguments are paths, lengths or citation keys are skipped.
- **Code listings** (`verbatim`, `lstlisting`, `minted`) are stepped over —
  a line of code is not prose.
- **The TOC is linked by construction**, since LaTeX generates it from the
  sectioning commands. The extractor gives TOC-eligible headings matching
  synthetic bookmark/anchor names. If every section is starred, the anchors
  stay legitimately empty and the linked check reports it.

---

## 10. Output (`reporter.py`) and entry point (`docval.py`)

```bash
python docval.py document.docx
python docval.py document.odt  --json
python docval.py document.tex  --structure structure.json --styles styles.json
```

Two output forms, both direct serializations of what the checks found:

- **Text** — one readable line per issue, with its location.
- **JSON** — `{file, checks_run, passed, issues[]}`. `checks_run` is recorded
  so "no issues" can be told apart from "that check was switched off".

**Exit codes are part of the interface**, because automation reads them
before reading any output:

| code | meaning |
|---|---|
| `0` | passed every enabled check |
| `1` | issues found |
| `2` | the file could not be checked (unsupported format) |

---

## 11. The test set: labeled sample ladders

Verification rests on a **labeled ladder**: nine versions of the same
document where each version fixes exactly one structural fault, so a check
must start passing at a known version and not before.

| version | what it adds / fixes |
|---|---|
| v1 | nothing is real — bold headings, typed TOC, typed list markers |
| v2 | real heading styles arrive, still unnumbered |
| v2a | content arrives, including an **uncaptioned picture of an equation** |
| v3 | that picture becomes a real equation |
| v4 | the equation moves into a footnote |
| v5 | heading bookmarks appear, still no TOC |
| v6 | a real, linked table of contents |
| v7 | automatic heading numbering |
| v8 | the research questions become a real numbered list — **clean** |
| v9 | *(Word/ODT only)* headings edited after the TOC was generated → stale |

The ladder exists in all three formats, and **all three report identically on
every version** — this is the single strongest evidence that the shared-rules
design works.

**Provenance, stated honestly:**

- **Word** — the original hand-built samples.
- **LaTeX** — authored to mirror them fault for fault. Each format fakes
  structure its own way: where Word has heading styles with numbering off and
  the number typed in, LaTeX turns `secnumdepth` down and types the number
  into the section title.
- **OpenDocument** — v1 and v2 authored in LibreOffice; **v2a–v9 converted**
  from the Word samples via `soffice --headless --convert-to odt`. The
  converted ones carry LibreOffice's fingerprints (automatic styles), so the
  two authored files are the more trustworthy reference.

v9 has no LaTeX counterpart: a stale table of contents cannot exist in LaTeX,
because it is regenerated from the sectioning commands on every build.

---

## 12. The test suite (`tests/`, pytest)

```bash
python -m pytest
```

**115 tests, ~3 seconds**, runnable from any directory (paths resolve from
the test file's own location, not the working directory).

| file | tests | what it covers |
|---|---|---|
| `test_ladders.py` | 39 | every version in all three formats, plus a strict `word == odt == latex` equality test |
| `test_rules.py` | 38 | each check alone, against `DocModel`s built by hand |
| `test_latex_constructs.py` | 21 | real-world LaTeX: chapters, parts, includes, run-in labels, listings, nested commands |
| `test_odt_constructs.py` | 9 | text reading (tabs, alt text) and numbering resolution, on XML fragments |
| `test_config.py` | 8 | property-file loading, merging, comments, typo detection |

Design points:

- **Hand-built `DocModel`s** cover what no real sample contains — a caption
  on the wrong side, a dangling TOC anchor, a typed bullet — in a few lines
  and with no file at all.
- **Ladder tests pass an explicit empty section list** rather than relying on
  whatever the built-in default happens to be, so they cannot silently change
  meaning when defaults are edited.
- **Every bug found in a real document became a test**, so none can quietly
  return.

The suite paid for itself immediately: on its first run it caught a stray `~`
(a LaTeX non-breaking space) surviving into caption text, which led to six
duplicated text-cleanup snippets becoming one helper.

---

## 13. File map

```
docval.py               entry point: dispatch, run, report, exit code
extractors.py           DocumentExtractor interface + registry
model.py                Block and DocModel — the shared representation
rules.py                the 11 checks + the engine
patterns.py             typed-structure detection, shared by all extractors
config.py               Structure/Styles loading over built-in defaults
reporter.py             text and JSON output

word_extractor.py       .docx  → DocModel
odt_extractor.py        .odt   → DocModel
latex_extractor.py      .tex   → DocModel
reader.py               the original .docx scaffold; superseded, kept for record

examples/               commented Structure and Styles templates
tests/                  pytest suite (115 tests)
Sample Documents/       Word/, LibreOffice/, LaTeX/ — the labeled ladders
requirements.txt        python-docx, TexSoup, pytest
pytest.ini              test discovery settings
```

**Dependencies: two at runtime** — `python-docx` (which brings `lxml`, used
directly for Word footnotes and for all ODT reading) and `TexSoup`. `pytest`
is development-only. Keeping this list short is deliberate: the tool is
destined for a CodeOcean container.

---

## 14. How it was built, in order

1. **Word reader → model → extractor.** Established the representation, and
   surfaced the two hard facts: numbering lives on the style, and heading
   detection must ignore style names.
2. **Rule engine, one check at a time**, each verified against the ladder
   before the next was added.
3. **Config, reporter, entry point** — the standalone tool.
4. **LaTeX extractor**, plus `patterns.py` extracted for sharing. First proof
   that one rule set judges two formats.
5. **Restructure** into the plugin architecture and the two property files,
   with all behaviour re-verified unchanged.
6. **Real-document hardening.** A genuine seminar report broke the LaTeX
   extractor in several ways at once; each fix is described in §9.3.
7. **Test suite** — the ladder verification, previously done by reading
   output by hand after every change, became 96 assertions.
8. **OpenDocument extractor** — three steps, no engine changes, 19 more tests.

---

## 15. Known gaps and next steps

**Unverified for lack of a labeled sample**
- The typed-equation pattern — no sample contains a keyboard-typed equation.
- An English-styled Word document, to prove locale independence in the other
  direction (all current Word samples have German internal style names).

**LaTeX coverage** (none produce *false* issues; they lose content)
- Custom macros (`\newcommand{\title}{…}` then `\title`) are not expanded.
- `\appendix` does not switch numbering to letters.
- `subfigure` / `subcaption` nested floats are not handled individually.
- Bibliography environments are not modelled.

**Sample provenance**
- ODT v2a–v9 are converted from Word rather than authored in LibreOffice.
- LaTeX samples are authored to mirror, not real student submissions.

**Planned work**
- **Reference-comparison mode** *(specifically requested by the supervisor)* —
  parse an instructor's model document into a `DocModel` and compare a
  submission's structure against it, instead of against fixed rules. The
  extractors are reused unchanged; what is new is deciding what "same
  structure" means (same section names? same heading-depth pattern? same
  counts and order of tables and figures? with what tolerance?).
- **CodeOcean packaging** — run inside the container; the JSON output and
  exit codes are the interface it will use.
- **Feedback layer** — generated natural-language explanations for students,
  using CodeOcean's existing capability, keyed on the stable check ids.

---

## 16. Repository

TU Ilmenau GitLab. Work is on the `develop` branch; `main` is protected.

Recent history:

```
cb48d1d  Give the LaTeX samples a real numbering fault
be3a1da  Add pytest suite
a07679f  Support real-world LaTeX documents
5bcf9c7  Merge develop and dev, resolve README conflict
8755094  Restructure into a plugin architecture with Structure and Styles properties
db3d08c  Add the LaTeX extractor; shared rules verified identical on both formats
51bd319  Add config, reporter, and entry point; complete the standalone Word tool
```

*(The OpenDocument extractor and its tests are complete but not yet
committed at the time of writing.)*
