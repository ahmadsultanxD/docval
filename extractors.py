"""
extractors.py - the plug-in socket that document formats connect to.

The engine never mentions a format by name. Instead, every format provides
one class that fulfils the DocumentExtractor contract below, and registers
one instance of it. From then on the entry point finds the right extractor
for a file by its extension, with no format-specific code anywhere else.

Adding support for a new format (say OpenOffice) is three steps:

  1. Write odt_extractor.py with a class that inherits DocumentExtractor,
     says which extensions it handles, and implements extract().
  2. At the bottom of that file, call register(OdtExtractor()).
  3. Add one import line in docval.py, because importing the module is
     what runs the register() call.

Nothing in rules.py, reporter.py, or config.py changes - the whole point
of the shared representation.
"""

import os
from abc import ABC, abstractmethod


class DocumentExtractor(ABC):
    """
    The contract a format must fulfil to plug into docval.

    An extractor's only job is to read one file format and produce the
    shared representation (a DocModel of Blocks). It must not judge the
    document - deciding what is an issue is the rule engine's job.
    """

    # The file extensions this extractor handles, lowercase, with the dot:
    # (".docx",) or (".tex", ".latex"). Filled in by each subclass.
    extensions = ()

    @abstractmethod
    def extract(self, path, styles=None):
        """Read the file and return a DocModel. The styles property set
        supplies the language tables (caption labels, list labels)."""


# The registry: extension -> the extractor instance responsible for it.
_registry = {}


def register(extractor):
    """Make an extractor available. Called once, where it is defined."""
    for extension in extractor.extensions:
        _registry[extension.lower()] = extractor


def extractor_for(path):
    """The registered extractor for this file, or None if none handles it."""
    extension = os.path.splitext(path)[1].lower()
    return _registry.get(extension)


def supported_extensions():
    """The extensions of every registered format, for error messages."""
    return sorted(_registry)
=======
"""
extractors.py - the plug-in socket that document formats connect to.

The engine never mentions a format by name. Instead, every format provides
one class that fulfils the DocumentExtractor contract below, and registers
one instance of it. From then on the entry point finds the right extractor
for a file by its extension, with no format-specific code anywhere else.

Adding support for a new format (say OpenOffice) is three steps:

  1. Write odt_extractor.py with a class that inherits DocumentExtractor,
     says which extensions it handles, and implements extract().
  2. At the bottom of that file, call register(OdtExtractor()).
  3. Add one import line in docval.py, because importing the module is
     what runs the register() call.

Nothing in rules.py, reporter.py, or config.py changes - the whole point
of the shared representation.
"""

import os
from abc import ABC, abstractmethod


class DocumentExtractor(ABC):
    """
    The contract a format must fulfil to plug into docval.

    An extractor's only job is to read one file format and produce the
    shared representation (a DocModel of Blocks). It must not judge the
    document - deciding what is an issue is the rule engine's job.
    """

    # The file extensions this extractor handles, lowercase, with the dot:
    # (".docx",) or (".tex", ".latex"). Filled in by each subclass.
    extensions = ()

    @abstractmethod
    def extract(self, path, styles=None):
        """Read the file and return a DocModel. The styles property set
        supplies the language tables (caption labels, list labels)."""


# The registry: extension -> the extractor instance responsible for it.
_registry = {}


def register(extractor):
    """Make an extractor available. Called once, where it is defined."""
    for extension in extractor.extensions:
        _registry[extension.lower()] = extractor


def extractor_for(path):
    """The registered extractor for this file, or None if none handles it."""
    extension = os.path.splitext(path)[1].lower()
    return _registry.get(extension)


def supported_extensions():
    """The extensions of every registered format, for error messages."""
    return sorted(_registry)