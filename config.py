"""
config.py - Step 5: everything that varies, in one place.

The checks' logic lives in code, but the POLICY they apply - which sections a
course requires, which caption labels and list labels each language uses,
which checks are active - belongs to the instructor, not the developer. In
production the code is packaged away (eventually inside CodeOcean) and cannot
be edited per course; this data can. So it lives here as plain data, and a
course can override any of it with a JSON file of the same shape, without
touching a line of code.

DEFAULTS is the complete built-in configuration: the tool runs with zero
setup, and a config file only overrides the keys it names. Overriding is
per top-level key and the file's value replaces the default entirely - no
deep merging - so what you write in the file is exactly what applies.
"""

import copy
import json


DEFAULTS = {
    # The sections a scientific document must contain. Each entry has the
    # canonical name (used in the issue message) and the heading texts that
    # satisfy it, so a German-language document passes the same requirement
    # ("Einleitung" satisfies "Introduction"). Matching normalizes case,
    # spacing, and typed numbers on both sides, so these entries stay
    # forgiving about how they are written. The German synonyms are
    # unverified until a German-text sample exists.
    "required_sections": [
        {"name": "Introduction",          "accept": ["introduction", "einleitung"]},
        {"name": "State of Research",     "accept": ["state of research", "related work",
                                                     "stand der forschung", "verwandte arbeiten"]},
        {"name": "Theoretical Framework", "accept": ["theoretical framework", "theoretischer rahmen",
                                                     "theoretische grundlagen"]},
        {"name": "Methodology",           "accept": ["methodology", "methods", "methodik", "methoden"]},
        {"name": "Results",               "accept": ["results", "ergebnisse"]},
        {"name": "Discussion",            "accept": ["discussion", "diskussion"]},
        {"name": "Conclusion",            "accept": ["conclusion", "fazit", "schlussfolgerung"]},
        {"name": "References",            "accept": ["references", "bibliography",
                                                     "literaturverzeichnis", "literatur"]},
    ],

    # Caption labels per caption kind. A real Word caption carries a hidden
    # SEQ field whose label names the sequence ("SEQ Table"), and the label
    # is localized - so each kind lists the labels of every language we
    # accept. The same words also recognize TYPED captions ("Table 1 ...").
    "caption_labels": {
        "table":  ["table", "tabelle"],
        "figure": ["figure", "abbildung"],
    },

    # Labeled list sequences we expect in scientific documents ("RQ1:").
    # In a real list the label comes from the numbering definition and never
    # appears in the text; typed as ordinary text it marks a fake. The list
    # is explicit and short on purpose: a generic letters-plus-digit pattern
    # would misfire on ordinary prose.
    "list_labels": ["RQ"],

    # Per-check switches, keyed by the check's stable id. A check missing
    # from this table is enabled; set an id to false to switch it off for
    # a course that does not require that piece of structure.
    "checks": {},
}


def load(path=None):
    """
    Return the active configuration: the defaults, with any keys from the
    given JSON file replacing them. A key the defaults do not know is an
    error rather than a silent no-op, so a typo in a config file ("cheks")
    fails loudly instead of quietly disabling nothing.
    """
    config = copy.deepcopy(DEFAULTS)
    if path is not None:
        with open(path, encoding="utf-8") as f:
            overrides = json.load(f)
        for key, value in overrides.items():
            if key not in DEFAULTS:
                raise KeyError(
                    f"Unknown configuration key {key!r}; "
                    f"expected one of: {', '.join(sorted(DEFAULTS))}")
            config[key] = value
    return config
