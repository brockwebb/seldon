"""Artifact naming grammar — the single definition point.

This module is a **leaf**: it imports nothing from Seldon. That is its whole
purpose. The Result name grammar is needed both by
``seldon.commands.result`` (which validates names on registration) and by
``seldon.paper.build`` (whose reference-token pattern embeds it), and
``seldon.commands.result`` already imports ``REFERENCE_PATTERN`` from
``seldon.paper.build``. Defining the grammar in either of those modules makes
the pair circular, which is what forced a lazy-compile workaround before this
module existed.

Anything that needs the grammar imports it from here. Nothing here imports
back.
"""
from __future__ import annotations

import re

# AD-028 §1, as amended by Amendment 01 (2026-09-04): the Result.name slug
# grammar. Case-sensitive, ASCII, safe in a filename or a URL fragment.
#
# THIS IS THE SINGLE DEFINITION POINT. The pattern string is written here and
# nowhere else: every name-accepting path imports this constant, and every
# message, `--help` string, domain-config description and convention doc that
# needs to show the grammar interpolates `RESULT_NAME_PATTERN.pattern` or
# describes it in words. `tests/test_result_grammar.py` pins that with a grep
# test over the whole repo. Do not paste the pattern anywhere else — a second
# copy is a second definition, and the two will drift.
RESULT_NAME_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]*$')

#: Maximum length of a Result name, in characters.
RESULT_NAME_MAX_LENGTH = 128

#: Human-readable rendering of RESULT_NAME_PATTERN, derived from the constant so
#: it cannot drift from it. Used in error messages and `--help` text.
RESULT_NAME_GRAMMAR_PROSE = (
    "must start with an ASCII letter or digit, then any of letters, digits, "
    "underscore, dot or hyphen"
)


def unanchored_name_grammar() -> str:
    """Return the Result name grammar with its ``^``/``$`` anchors stripped.

    ``RESULT_NAME_PATTERN`` is anchored because it validates a whole name.
    Embedding it inside a larger pattern — the reference token in
    ``seldon.paper.build`` — needs the same character sequence *without* the
    anchors. Deriving it here keeps the single definition point intact: the
    grammar is never restated.

    Returns:
        The pattern source between the anchors (the body of ``^...$``).

    Raises:
        ValueError: If RESULT_NAME_PATTERN stops being a fully anchored
            pattern. Silently embedding a stray ``^`` or ``$`` inside a larger
            pattern would make every token stop matching, so this fails loudly
            rather than degrading.
    """
    source = RESULT_NAME_PATTERN.pattern
    if not (source.startswith("^") and source.endswith("$")):
        raise ValueError(
            "RESULT_NAME_PATTERN is expected to be a fully anchored pattern "
            f"(^...$); got {source!r}. Callers embed its unanchored body and "
            "cannot do so safely otherwise."
        )
    return source[1:-1]
