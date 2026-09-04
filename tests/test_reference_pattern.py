"""`REFERENCE_PATTERN` uses the AD-028 name grammar, so a document can document
its own syntax.

Graph task `3376805b`. The pattern used to accept any character but ':' and '}'
in the name position, so the documentation placeholder ``{{result:<NAME>:value}}``
— written in prose while *explaining* the token syntax to a reader — matched,
and the resolver reported SI-01 "artifact not found" on the explanation. Two
ai-readiness-kg documents carry that placeholder, which is why that project's
shim had to pre-filter tokens through a stricter grammar of its own before
handing them to this library.

The fix reuses the single definition point of the Result name grammar,
``seldon.commands.result.RESULT_NAME_PATTERN`` (AD-028 §1, amended 2026-09-04 to
admit uppercase), for the name capture. A token whose name is not a legal name
is not a token.
"""
from __future__ import annotations

import re

import pytest

from seldon.commands.result import RESULT_NAME_PATTERN
from seldon.paper.build import REFERENCE_PATTERN, resolve_references


# ---------------------------------------------------------------------------
# The defect, and the amendment it depends on
# ---------------------------------------------------------------------------

def test_documentation_placeholder_is_not_a_reference():
    """`{{result:<NAME>:value}}` is prose about the syntax, not a token."""
    assert REFERENCE_PATTERN.search("{{result:<NAME>:value}}") is None


def test_a_legal_uppercase_leading_name_is_a_reference():
    """`{{result:G1_x:value}}` is a token.

    G1_x is uppercase-leading, legal only since the 2026-09-04 amendment to
    AD-028 §1. This pins that the amendment is actually wired into
    REFERENCE_PATTERN rather than only into `seldon result register`.
    """
    match = REFERENCE_PATTERN.search("{{result:G1_x:value}}")
    assert match is not None
    assert match.group(1) == "result"
    assert match.group(2) == "G1_x"
    assert match.group(3) == "value"


def test_placeholder_and_real_token_in_the_same_document():
    """The exact ai-readiness-kg shape: a memo that explains and then uses."""
    text = (
        "Reference a registered value with `{{result:<NAME>:value}}`.\n"
        "For example, the gate admitted {{result:G1_x:value}} documents.\n"
    )
    names = [m.group(2) for m in REFERENCE_PATTERN.finditer(text)]
    assert names == ["G1_x"]


def test_resolver_reports_nothing_on_a_documentation_placeholder():
    """No SI-01, and the prose comes back untouched — no pre-filter needed."""
    text = "Write `{{result:<NAME>:value}}` to reference a Result."
    resolved, errors = resolve_references(text, {}, "design_decisions.md")

    assert resolved == text
    assert errors == []


# ---------------------------------------------------------------------------
# The grammar is the Result name grammar, derived not copied
# ---------------------------------------------------------------------------

def test_name_capture_is_the_result_name_grammar_verbatim():
    """The name capture embeds RESULT_NAME_PATTERN's body, anchors stripped.

    AD-028 gives the grammar exactly one definition point. This asserts the
    embedding is derived from that constant, so amending the constant amends
    the token pattern with it — there is no second copy to drift.
    """
    unanchored = RESULT_NAME_PATTERN.pattern.lstrip("^").rstrip("$")
    assert f"({unanchored})" in REFERENCE_PATTERN.pattern


@pytest.mark.parametrize("name", ["g1_x", "G1_x", "X", "0", "a.b-c_d", "F1",
                                  "Smith2020", "attractor_density_T1000"])
def test_legal_names_match(name):
    assert RESULT_NAME_PATTERN.match(name)
    assert REFERENCE_PATTERN.search("{{result:%s:value}}" % name) is not None


@pytest.mark.parametrize("name", ["<NAME>", "<n>", "_leading", "-leading",
                                  ".leading", "has space", "a/b", "a+b", "a|b",
                                  ""])
def test_illegal_names_do_not_match(name):
    assert not RESULT_NAME_PATTERN.match(name)
    assert REFERENCE_PATTERN.search("{{result:%s:value}}" % name) is None


# ---------------------------------------------------------------------------
# figure and cite share the grammar
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("token,name", [
    ("{{figure:F1:path}}", "F1"),
    ("{{figure:fig_convergence:path}}", "fig_convergence"),
    ("{{cite:Smith2020:bibtex_key}}", "Smith2020"),
    ("{{cite:smith_2023:bibtex_key}}", "smith_2023"),
])
def test_figure_and_cite_names_still_match(token, name):
    """Every figure/cite name in this repo's fixtures is a legal artifact name.

    A `cite` token names a Citation *artifact*; the BibTeX key it carries lives
    in that artifact's `bibtex_key` property (checked by SI-07), not in the
    token. Narrowing the token grammar therefore constrains no BibTeX key.
    """
    match = REFERENCE_PATTERN.search(token)
    assert match is not None and match.group(2) == name


@pytest.mark.parametrize("token", ["{{figure:<NAME>:path}}",
                                   "{{cite:<NAME>:bibtex_key}}"])
def test_figure_and_cite_placeholders_are_not_references(token):
    assert REFERENCE_PATTERN.search(token) is None


# ---------------------------------------------------------------------------
# The lazy pattern is indistinguishable from a compiled one
# ---------------------------------------------------------------------------

def test_reference_pattern_behaves_as_a_compiled_pattern():
    """Callers do `from seldon.paper.build import REFERENCE_PATTERN` and then
    call finditer/sub/findall on it.

    This was written against a lazy-compiling wrapper that existed to break the
    build↔result import cycle. Hoisting the grammar into the leaf module
    `seldon.core.naming` removed the cycle and the wrapper, so this is now a
    plain `re.Pattern` — the assertions are kept because they pin the caller-
    visible surface either way.
    """
    text = "{{result:a:value}} and {{cite:b2020:key}}"

    assert REFERENCE_PATTERN.findall(text) == [
        ("result", "a", "value"), ("cite", "b2020", "key")
    ]
    assert [m.group(2) for m in REFERENCE_PATTERN.finditer(text)] == ["a", "b2020"]
    assert REFERENCE_PATTERN.sub("X", text) == "X and X"
    assert isinstance(REFERENCE_PATTERN.pattern, str)
    assert isinstance(REFERENCE_PATTERN, re.Pattern)


def test_reference_pattern_importable_from_either_direction():
    """`seldon.commands.result` imports REFERENCE_PATTERN at its own top level
    while defining the grammar REFERENCE_PATTERN needs. Both modules must
    import cleanly whichever is reached first."""
    import subprocess
    import sys

    for first in ("seldon.paper.build", "seldon.commands.result"):
        proc = subprocess.run(
            [sys.executable, "-c",
             f"import {first}; "
             "from seldon.paper.build import REFERENCE_PATTERN; "
             "assert REFERENCE_PATTERN.search('{{result:G1_x:value}}')"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, f"{first} first: {proc.stderr}"


def test_grammar_derivation_rejects_an_unanchored_constant():
    """If the single definition point stops being anchored, fail loudly.

    Embedding a stray `^` or `$` inside REFERENCE_PATTERN would make every
    token silently stop matching, so the derivation refuses rather than
    degrades.
    """
    import seldon.core.naming as naming

    original = naming.RESULT_NAME_PATTERN
    naming.RESULT_NAME_PATTERN = re.compile(r'[a-z]+')
    try:
        with pytest.raises(ValueError) as exc:
            naming.unanchored_name_grammar()
        assert "anchored" in str(exc.value)
    finally:
        naming.RESULT_NAME_PATTERN = original
