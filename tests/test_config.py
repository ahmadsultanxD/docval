"""
test_config.py - loading the Structure and Styles property files.

These files are the part of the project an instructor actually edits, so
how they behave matters as much as the checks themselves: what happens when
a file names only one setting, when it contains a comment, and when someone
mistypes a key.
"""

import json

import pytest

import config


def write_json(folder, name, data):
    path = folder / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def test_the_defaults_apply_when_no_file_is_given():
    """The tool runs with no setup at all."""
    assert config.load_styles(None) == config.DEFAULT_STYLES
    assert config.load_structure(None) == config.DEFAULT_STRUCTURE


def test_a_file_only_needs_the_settings_it_changes(tmp_path):
    """
    Naming one setting inside a group must not wipe out the others: a file
    that sets the heading step should keep the default starting level.
    """
    path = write_json(tmp_path, "styles.json",
                      {"headings": {"max_deeper_step": 2}})
    styles = config.load_styles(path)
    assert styles["headings"]["max_deeper_step"] == 2
    assert styles["headings"]["first_level"] == \
        config.DEFAULT_STYLES["headings"]["first_level"]
    assert styles["captions"] == config.DEFAULT_STYLES["captions"]


def test_comments_are_ignored(tmp_path):
    """A property file documents itself with keys starting with "_"."""
    path = write_json(tmp_path, "styles.json", {
        "_comment": "why this course does it this way",
        "headings": {"_comment": "no skipped levels", "max_deeper_step": 1},
    })
    styles = config.load_styles(path)
    assert "_comment" not in styles
    assert "_comment" not in styles["headings"]


def test_an_unknown_key_fails_loudly(tmp_path):
    """
    A typo must not quietly do nothing: "cheks" would switch nothing off
    and the instructor would never know.
    """
    path = write_json(tmp_path, "styles.json", {"cheks": {}})
    with pytest.raises(KeyError):
        config.load_styles(path)


def test_the_sections_list_can_be_emptied(tmp_path):
    """How a course says it does not care which sections a document has."""
    path = write_json(tmp_path, "structure.json", {"sections": []})
    assert config.load_structure(path)["sections"] == []


def test_a_course_can_define_its_own_sections(tmp_path):
    path = write_json(tmp_path, "structure.json", {"sections": [
        {"name": "Experiments", "accept": ["experiments", "experimente"]},
    ]})
    sections = config.load_structure(path)["sections"]
    assert [s["name"] for s in sections] == ["Experiments"]


def test_loading_does_not_change_the_defaults(tmp_path):
    """
    Each load starts from a fresh copy. Without that, checking one document
    with a course's file would change how the next one is checked.
    """
    before = json.dumps(config.DEFAULT_STYLES, sort_keys=True)
    path = write_json(tmp_path, "styles.json",
                      {"lists": {"labels": ["RQ", "H"]}})
    config.load_styles(path)
    assert json.dumps(config.DEFAULT_STYLES, sort_keys=True) == before


def test_a_custom_list_label_reaches_the_extractor(tmp_path):
    """
    The whole point of the Styles file: a course names its own labelled
    sequence and the extractor recognizes it, with no code change.
    """
    import latex_extractor

    source = tmp_path / "hypotheses.tex"
    source.write_text(r"""
\documentclass{article}
\begin{document}
\section{Hypotheses}
H1: Larger populations coordinate worse.
\end{document}
""", encoding="utf-8")

    styles = config.load_styles(write_json(tmp_path, "styles.json",
                                           {"lists": {"labels": ["H"]}}))
    model = latex_extractor.extract(str(source), styles)
    typed = [b for b in model.blocks if b.type == "list_item" and not b.real]
    assert len(typed) == 1
