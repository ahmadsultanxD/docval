"""
test_latex_constructs.py - the LaTeX the sample ladder never contained.

Every test here comes from a real document breaking the extractor. The
authored samples are deliberately simple, so they exercised only a narrow
slice of LaTeX; the first genuine report brought chapters, run-in labels,
title pages and nested commands, and each of those was a bug. Writing them
down here means none of them can quietly come back.

Each test builds the smallest .tex file that shows the behaviour, in
pytest's own temporary folder, so the tests need nothing from the disk.
"""

import pytest

from conftest import checks_fired, issue_counts


def write_tex(folder, name, body):
    """Write a .tex file into the temporary folder and return its path."""
    path = folder / name
    path.write_text(body, encoding="utf-8")
    return str(path)


def headings_of(path):
    """The (level, text, numbered) of every heading the extractor found."""
    import latex_extractor

    model = latex_extractor.extract(path)
    return [(b.level, b.text, b.numbered)
            for b in model.blocks if b.type == "heading"]


# --- how deep a heading sits, which depends on the document class ------------

def test_article_starts_at_section(tmp_path):
    """In an article there is no chapter, so \\section is the top level."""
    path = write_tex(tmp_path, "article.tex", r"""
\documentclass{article}
\begin{document}
\section{Introduction}
\subsection{Motivation}
\end{document}
""")
    assert headings_of(path) == [(1, "Introduction", True),
                                 (2, "Motivation", True)]


def test_report_class_puts_chapter_on_top(tmp_path):
    """
    A report starts at \\chapter, which pushes every other level down one.

    Reading a report with the article table was the bug that reported seven
    invented "skipped level" issues in a real document.
    """
    path = write_tex(tmp_path, "report.tex", r"""
\documentclass{report}
\begin{document}
\chapter{Introduction}
\section{Motivation}
\subsection{Scope}
\end{document}
""")
    assert headings_of(path) == [(1, "Introduction", True),
                                 (2, "Motivation", True),
                                 (3, "Scope", True)]


def test_unknown_class_using_chapter_is_recognized(tmp_path):
    """
    A thesis template usually defines a class of its own on top of book or
    report, and we cannot know its name. Using \\chapter at all is the
    document telling us what kind of document it is.
    """
    path = write_tex(tmp_path, "thesis.tex", r"""
\documentclass{someuniversitythesis}
\begin{document}
\chapter{Introduction}
\section{Background}
\end{document}
""")
    assert headings_of(path) == [(1, "Introduction", True),
                                 (2, "Background", True)]


def test_part_pushes_everything_down_again(tmp_path):
    """\\part is the widest division of all, above \\chapter."""
    path = write_tex(tmp_path, "parts.tex", r"""
\documentclass{book}
\begin{document}
\part{Foundations}
\chapter{Introduction}
\section{Motivation}
\subsection{Scope}
\end{document}
""")
    assert [level for level, _, _ in headings_of(path)] == [1, 2, 3, 4]


def test_report_leaves_subsubsection_unnumbered(tmp_path):
    """
    A report numbers one level less deeply than an article, so its
    \\subsubsection is unnumbered by default. That is the class working as
    designed, not a fault, and must not be reported as one.
    """
    path = write_tex(tmp_path, "depth.tex", r"""
\documentclass{report}
\begin{document}
\chapter{Introduction}
\subsubsection{A Detail}
\end{document}
""")
    levels = headings_of(path)
    assert levels[-1] == (4, "A Detail", False)
    assert "heading-numbering" not in checks_fired_for(path)


def checks_fired_for(path):
    """The checks that reported something for this file."""
    import latex_extractor

    return checks_fired(latex_extractor.extract(path))


# --- what counts as a numbering fault in LaTeX -------------------------------

def test_unnumbered_sections_are_not_a_fault(tmp_path):
    """
    LaTeX numbers sections by itself, so \\section* is a deliberate choice -
    exactly how an Abstract or an Acknowledgements section is written. It is
    not the missing structure that the same thing means in Word.
    """
    path = write_tex(tmp_path, "starred.tex", r"""
\documentclass{article}
\begin{document}
\section*{Abstract}
\section{Introduction}
\section*{Acknowledgements}
\end{document}
""")
    assert "heading-numbering" not in checks_fired_for(path)


def test_number_typed_into_a_title_is_a_fault(tmp_path):
    """The real fault: numbering the heading by hand instead of letting
    LaTeX do it."""
    path = write_tex(tmp_path, "typed.tex", r"""
\documentclass{article}
\begin{document}
\section*{2. Related Work}
\end{document}
""")
    assert issue_counts_for(path)["heading-numbering"] == 1


def test_a_title_starting_with_a_digit_is_not_a_typed_number(tmp_path):
    """"3D Printing" begins with a digit but is not a numbered heading."""
    path = write_tex(tmp_path, "3d.tex", r"""
\documentclass{article}
\begin{document}
\section*{3D Printing Methods}
\section*{5G Network Analysis}
\end{document}
""")
    assert "heading-numbering" not in checks_fired_for(path)


def issue_counts_for(path):
    """The issue counts for one .tex file."""
    import latex_extractor

    return issue_counts(latex_extractor.extract(path))


# --- run-in labels, which are not headings -----------------------------------

def test_paragraph_is_a_run_in_label_not_a_heading(tmp_path):
    """
    \\paragraph sets its title in bold and continues the text on the same
    line. LaTeX neither numbers it nor lists it in the table of contents,
    so it is not part of the outline. Treating it as heading level 4 made
    every ordinary "\\subsection then \\paragraph" pair look like a skipped
    level.
    """
    path = write_tex(tmp_path, "runin.tex", r"""
\documentclass{article}
\begin{document}
\section{Challenges}
\subsection{Overview}
\paragraph{Credit Assignment.} When many agents contribute to one outcome,
attributing credit is ambiguous.
\end{document}
""")
    assert [level for level, _, _ in headings_of(path)] == [1, 2]
    assert "heading-hierarchy" not in checks_fired_for(path)


def test_a_run_in_label_is_not_a_typed_list_marker(tmp_path):
    """
    A run-in label lands at the front of its paragraph, so a label like
    "RQ1:" looks exactly like a typed list marker. It is not: the author
    used a real LaTeX command, and three discussion paragraphs must not be
    reported as a faked list.
    """
    path = write_tex(tmp_path, "rq.tex", r"""
\documentclass{article}
\begin{document}
\section{Findings}
\paragraph{RQ1: Scalability approaches.} The three approaches differ.

\paragraph{RQ2: Training paradigms.} The paradigms cut across them.
\end{document}
""")
    assert "list-formatting" not in checks_fired_for(path)


def test_a_genuinely_typed_list_is_still_caught(tmp_path):
    """The check still does its job when the marker really was typed."""
    path = write_tex(tmp_path, "typedlist.tex", r"""
\documentclass{article}
\begin{document}
\section{Questions}
RQ1: What data sources are used?

RQ2: Which algorithms are applied?
\end{document}
""")
    assert issue_counts_for(path)["list-formatting"] == 2


# --- text that is not text ---------------------------------------------------

def test_image_paths_and_lengths_never_become_text(tmp_path):
    """
    A file path is not prose. TexSoup hands back the arguments of every
    command as if they were visible text, so a title page logo once read as
    "height=2cmpics/logo.jpg" and was reported as a typed equation, because
    it contains an "=" and a "/".
    """
    path = write_tex(tmp_path, "logo.tex", r"""
\documentclass{article}
\begin{document}
\begin{titlepage}
\begin{center}
\includegraphics[height=2cm]{pics/logo-thi.jpg}
\vspace{1cm}
TECHNISCHE UNIVERSITAT ILMENAU
\end{center}
\end{titlepage}
\section{Introduction}
\end{document}
""")
    import latex_extractor

    model = latex_extractor.extract(path)
    all_text = " ".join(b.text for b in model.blocks)
    assert "logo-thi" not in all_text
    assert "height=2cm" not in all_text
    assert "equation-format" not in checks_fired_for(path)


def test_a_command_nested_in_a_caption_does_not_crash(tmp_path):
    """
    A citation or acronym macro inside a caption is ordinary LaTeX, and it
    used to raise an AttributeError before the caption was ever read.
    """
    path = write_tex(tmp_path, "nested.tex", r"""
\documentclass{article}
\begin{document}
\begin{figure}
\includegraphics{plot.png}
\caption{Architecture of the \textbf{CNN} model~\cite{smith2020}}
\end{figure}
\end{document}
""")
    import latex_extractor

    captions = [b.text for b in latex_extractor.extract(path).blocks
                if b.type == "caption"]
    assert captions == ["Architecture of the CNN model"]


def test_code_listings_are_not_read_as_prose(tmp_path):
    """
    A line of code is not a formula typed instead of an equation. Without
    stepping over listings, "rate = alpha * decay" inside one would be
    reported as a typed equation.
    """
    path = write_tex(tmp_path, "code.tex", r"""
\documentclass{article}
\begin{document}
\section{Implementation}
\begin{lstlisting}
rate = alpha * decay + bias
\end{lstlisting}
\end{document}
""")
    assert "equation-format" not in checks_fired_for(path)


def test_a_formula_typed_in_prose_is_still_caught(tmp_path):
    """Outside a listing, a typed formula is exactly what it looks like."""
    path = write_tex(tmp_path, "formula.tex", r"""
\documentclass{article}
\begin{document}
\section{Metrics}
The F1-score is F1 = 2 * P * R / (P + R) in our setting.
\end{document}
""")
    assert issue_counts_for(path)["equation-format"] == 1


# --- documents made of several files -----------------------------------------

def test_included_files_are_read(tmp_path):
    """
    A thesis keeps one file per chapter. Reading only the main file would
    find a document with no content at all.
    """
    (tmp_path / "chapters").mkdir()
    (tmp_path / "chapters" / "intro.tex").write_text(
        "\\chapter{Introduction}\nOpening text.\n", encoding="utf-8")
    (tmp_path / "chapters" / "methods.tex").write_text(
        "\\chapter{Methodology}\nHow it was done.\n", encoding="utf-8")
    path = write_tex(tmp_path, "main.tex", r"""
\documentclass{book}
\begin{document}
\input{chapters/intro}
\include{chapters/methods}
\end{document}
""")
    titles = [text for _, text, _ in headings_of(path)]
    assert titles == ["Introduction", "Methodology"]


def test_a_missing_included_file_is_skipped(tmp_path):
    """
    A submission may reference a file we do not have. The rest of the
    document is still worth checking, so this must not raise.
    """
    path = write_tex(tmp_path, "main.tex", r"""
\documentclass{article}
\begin{document}
\input{chapters/does-not-exist}
\section{Introduction}
\end{document}
""")
    assert [text for _, text, _ in headings_of(path)] == ["Introduction"]


def test_a_file_including_itself_does_not_loop(tmp_path):
    """A guard against a document that pulls in its own source."""
    path = write_tex(tmp_path, "loop.tex", r"""
\documentclass{article}
\begin{document}
\input{loop}
\section{Introduction}
\end{document}
""")
    assert [text for _, text, _ in headings_of(path)] == ["Introduction"]


def test_includegraphics_is_not_mistaken_for_include(tmp_path):
    """
    "\\includegraphics" begins with the letters of "\\include". Splicing in
    a file called "plot.png" would be nonsense, so the two are told apart.
    """
    path = write_tex(tmp_path, "graphics.tex", r"""
\documentclass{article}
\begin{document}
\begin{figure}
\includegraphics{plot.png}
\caption{A figure}
\end{figure}
\end{document}
""")
    import latex_extractor

    kinds = [b.type for b in latex_extractor.extract(path).blocks]
    assert "figure" in kinds


# --- floats that span both columns of a two-column paper ---------------------

@pytest.mark.parametrize("environment, kind", [("table", "table"),
                                               ("figure", "figure")])
def test_starred_floats_are_recognized(tmp_path, environment, kind):
    """
    Conference papers use figure* and table* for floats spanning both
    columns. They are the same thing as the unstarred form, and their
    captions must be found in the same way.
    """
    inner = ("\\begin{tabular}{ll}a & b\\\\\\end{tabular}"
             if kind == "table" else "\\includegraphics{plot.png}")
    order = ("\\caption{A wide float}\n" + inner if kind == "table"
             else inner + "\n\\caption{A wide float}")
    path = write_tex(tmp_path, "wide.tex", r"""
\documentclass{article}
\begin{document}
\begin{%s*}
%s
\end{%s*}
\end{document}
""" % (environment, order, environment))

    import latex_extractor

    model = latex_extractor.extract(path)
    captions = [b for b in model.blocks if b.type == "caption"]
    assert len(captions) == 1 and captions[0].kind == kind
    assert f"{kind}-caption" not in checks_fired_for(path)
