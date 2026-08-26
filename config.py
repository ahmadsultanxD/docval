"""
config.py - loading the Structure and Styles property files.

The engine is generic: nothing in the code knows what one course requires
or how one kind of document should look. Everything specific lives in two
JSON property files that an instructor edits without touching code:

  Structure - WHAT the document must contain: the required sections, in
              the order they are expected to appear. If the sections list
              is empty, no section requirements apply at all - the document
              may contain any sections, as long as they are properly
              structured (the Styles rules always apply).

  Styles    - HOW the document must be formatted: the heading hierarchy
              rules, where captions belong, which words label captions in
              which language, which custom list labels exist (like "RQ"
              for research questions), and which checks are active.

Both files are optional. The defaults below are complete, so the tool runs
with zero setup; a property file only overrides what it names. Inside a
group ("headings", "captions", ...) the file also only needs the keys it
changes - the rest keep their defaults. Keys starting with "_" are treated
as comments and ignored, so files can document themselves.
"""

import copy
import json


DEFAULT_STRUCTURE = {
    # The required sections. Right now it will not enforce the required sections.
    # If we have to verify that the sections are present in the document, add them in ordered
    # form in the json file.
    "sections": [],
}


DEFAULT_STYLES = {
    # How the heading hierarchy must be built: the level the document
    # starts at, and how much deeper one heading may go than the heading
    # before it (1 means a level may never be skipped: level 1 to level 2
    # is fine, level 1 to level 3 is an issue).
    "headings": {
        "first_level": 1,
        "max_deeper_step": 1,
    },

    # Where captions belong relative to their table or figure ("above" or
    # "below"), and which words label a caption of each kind. The labels
    # are localized, so each kind lists every accepted language's word;
    # the same words also recognize TYPED captions ("Table 1 ...").
    "captions": {
        "table_position": "above",
        "figure_position": "below",
        "labels": {
            "table":  ["table", "tabelle"],
            "figure": ["figure", "abbildung"],
        },
    },

    # Custom labeled list sequences expected in the documents ("RQ1:" for
    # research questions). In a real list the label comes from the format's
    # numbering machinery and never appears in the text; typed as ordinary
    # text it marks a fake.
    "lists": {
        "labels": ["RQ"],
    },

    # Per-check switches, keyed by the check's stable id. A check missing
    # from this table is enabled; set an id to false to switch it off for
    # a course that does not require that piece of structure.
    "checks": {},
}


def load_structure(path=None):
    """The active Structure: the defaults, overridden by the given file."""
    return _load(DEFAULT_STRUCTURE, path)


def load_styles(path=None):
    """The active Styles: the defaults, overridden by the given file."""
    return _load(DEFAULT_STYLES, path)


def _load(defaults, path):
    """
    Start from the defaults and apply the overrides from a JSON file.

    A key the defaults do not know is an error rather than a silent no-op,
    so a typo in a property file ("cheks") fails loudly instead of quietly
    disabling nothing. Keys starting with "_" are comments and skipped.
    When a default value is a group (a dictionary), the file's group is
    merged into it key by key, so the file only needs the entries it
    actually changes.
    """
    config = copy.deepcopy(defaults)
    if path is None:
        return config

    with open(path, encoding="utf-8") as f:
        overrides = json.load(f)

    for key, value in overrides.items():
        if key.startswith("_"):
            continue
        if key not in defaults:
            raise KeyError(
                f"Unknown property {key!r}; "
                f"expected one of: {', '.join(sorted(defaults))}")
        if isinstance(config[key], dict) and isinstance(value, dict):
            for inner_key, inner_value in value.items():
                if not inner_key.startswith("_"):
                    config[key][inner_key] = inner_value
        else:
            config[key] = value
    return config
=======
"""
config.py - loading the Structure and Styles property files.

The engine is generic: nothing in the code knows what one course requires
or how one kind of document should look. Everything specific lives in two
JSON property files that an instructor edits without touching code:

  Structure - WHAT the document must contain: the required sections, in
              the order they are expected to appear. If the sections list
              is empty, no section requirements apply at all - the document
              may contain any sections, as long as they are properly
              structured (the Styles rules always apply).

  Styles    - HOW the document must be formatted: the heading hierarchy
              rules, where captions belong, which words label captions in
              which language, which custom list labels exist (like "RQ"
              for research questions), and which checks are active.

Both files are optional. The defaults below are complete, so the tool runs
with zero setup; a property file only overrides what it names. Inside a
group ("headings", "captions", ...) the file also only needs the keys it
changes - the rest keep their defaults. Keys starting with "_" are treated
as comments and ignored, so files can document themselves.
"""

import copy
import json


DEFAULT_STRUCTURE = {
    # The required sections. Right now it will not enforce the required sections.
    # If we have to verify that the sections are present in the document, add them in ordered
    # form in the json file.
    "sections": [],
}


DEFAULT_STYLES = {
    # How the heading hierarchy must be built: the level the document
    # starts at, and how much deeper one heading may go than the heading
    # before it (1 means a level may never be skipped: level 1 to level 2
    # is fine, level 1 to level 3 is an issue).
    "headings": {
        "first_level": 1,
        "max_deeper_step": 1,
    },

    # Where captions belong relative to their table or figure ("above" or
    # "below"), and which words label a caption of each kind. The labels
    # are localized, so each kind lists every accepted language's word;
    # the same words also recognize TYPED captions ("Table 1 ...").
    "captions": {
        "table_position": "above",
        "figure_position": "below",
        "labels": {
            "table":  ["table", "tabelle"],
            "figure": ["figure", "abbildung"],
        },
    },

    # Custom labeled list sequences expected in the documents ("RQ1:" for
    # research questions). In a real list the label comes from the format's
    # numbering machinery and never appears in the text; typed as ordinary
    # text it marks a fake.
    "lists": {
        "labels": ["RQ"],
    },

    # Per-check switches, keyed by the check's stable id. A check missing
    # from this table is enabled; set an id to false to switch it off for
    # a course that does not require that piece of structure.
    "checks": {},
}


def load_structure(path=None):
    """The active Structure: the defaults, overridden by the given file."""
    return _load(DEFAULT_STRUCTURE, path)


def load_styles(path=None):
    """The active Styles: the defaults, overridden by the given file."""
    return _load(DEFAULT_STYLES, path)


def _load(defaults, path):
    """
    Start from the defaults and apply the overrides from a JSON file.

    A key the defaults do not know is an error rather than a silent no-op,
    so a typo in a property file ("cheks") fails loudly instead of quietly
    disabling nothing. Keys starting with "_" are comments and skipped.
    When a default value is a group (a dictionary), the file's group is
    merged into it key by key, so the file only needs the entries it
    actually changes.
    """
    config = copy.deepcopy(defaults)
    if path is None:
        return config

    with open(path, encoding="utf-8") as f:
        overrides = json.load(f)

    for key, value in overrides.items():
        if key.startswith("_"):
            continue
        if key not in defaults:
            raise KeyError(
                f"Unknown property {key!r}; "
                f"expected one of: {', '.join(sorted(defaults))}")
        if isinstance(config[key], dict) and isinstance(value, dict):
            for inner_key, inner_value in value.items():
                if not inner_key.startswith("_"):
                    config[key][inner_key] = inner_value
        else:
            config[key] = value
    return config