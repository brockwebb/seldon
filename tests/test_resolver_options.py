"""`resolve_references` caller options — the two knobs that retire a shim.

Graph task `f6b32bbe`. The ai-readiness-kg resolver shim
(`scripts/g1_resolve_results.py`) called this library and then lied to it twice,
because the library gave it no honest way to say what it meant:

1. It **pre-rendered the value into the index** it handed to the library, so an
   integral float registered as ``26.0`` would print as ``26`` in a sentence
   that had always read "26".
2. It **presented the artifact state as accepted**, so that ``allow_proposed``
   would resolve the token without the library stamping ``(proposed)`` onto
   every number in a working document where every Result is proposed.

Both are library contract, not shim business. The tests below assert the
library now expresses both directly, from an artifact node that is *not*
doctored: state stays ``proposed`` and value stays ``26.0``.

The corresponding removal condition is recorded in that shim's docstring.
"""
from __future__ import annotations

import pytest

from seldon.paper.build import PROPOSED_MARKER, resolve_references


def _node(name: str, *, state: str = "verified", value=1.0) -> dict:
    """An artifact node as `load_named_artifacts` yields it."""
    return {
        "artifact_id": f"id-{name}",
        "artifact_type": "Result",
        "name": name,
        "state": state,
        "value": value,
        "units": "",
        "description": f"{name} for test",
    }


def _integral_float_formatter(value):
    """The shim's `_render_value`: a count must not render as '26.0'."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


# ---------------------------------------------------------------------------
# Workaround 1: value_formatter replaces pre-rendering the index
# ---------------------------------------------------------------------------

def test_value_formatter_renders_integral_float_without_trailing_zero():
    """26.0 in the graph renders as '26' — no pre-rendered index needed."""
    artifacts = {"result:count": _node("count", value=26.0)}

    resolved, errors = resolve_references(
        "there are {{result:count:value}} rows",
        artifacts,
        "test.md",
        value_formatter=_integral_float_formatter,
    )

    assert resolved == "there are 26 rows"
    assert errors == []
    # The index was not doctored: the library still holds the real float.
    assert artifacts["result:count"]["value"] == 26.0


def test_value_formatter_defaults_to_str():
    """Default rendering is byte-for-byte what it was before the option."""
    artifacts = {"result:count": _node("count", value=26.0)}

    resolved, errors = resolve_references(
        "there are {{result:count:value}} rows", artifacts, "test.md"
    )

    assert resolved == "there are 26.0 rows"
    assert errors == []


def test_value_formatter_applies_to_non_float_fields_too():
    """The hook is a rendering hook, not a number hook."""
    artifacts = {"result:count": _node("count", value=26.0)}

    resolved, _errors = resolve_references(
        "{{result:count:description}}",
        artifacts,
        "test.md",
        value_formatter=lambda v: str(v).upper(),
    )

    assert resolved == "COUNT FOR TEST"


def test_value_formatter_returning_non_str_fails_loudly():
    """A caller bug is raised at the token, not swallowed inside re.sub."""
    artifacts = {"result:count": _node("count", value=26.0)}

    with pytest.raises(TypeError) as exc:
        resolve_references(
            "{{result:count:value}}",
            artifacts,
            "test.md",
            value_formatter=int,
        )

    assert "value_formatter" in str(exc.value)
    assert "{{result:count:value}}" in str(exc.value)


# ---------------------------------------------------------------------------
# Workaround 2: mark_proposed replaces faking the artifact state
# ---------------------------------------------------------------------------

def test_mark_proposed_false_renders_bare_value_from_a_proposed_result():
    """A proposed Result renders bare — without faking its state as accepted."""
    artifacts = {"result:rate": _node("rate", state="proposed", value=7.5)}

    resolved, errors = resolve_references(
        "{{result:rate:value}}",
        artifacts,
        "test.md",
        allow_proposed=True,
        mark_proposed=False,
    )

    assert resolved == "7.5"
    assert PROPOSED_MARKER not in resolved
    # The index was not doctored: the artifact is still proposed.
    assert artifacts["result:rate"]["state"] == "proposed"


def test_mark_proposed_false_still_reports_the_proposed_token():
    """Suppressing the marker suppresses no information.

    The shim's claim that "the information is not lost" is what makes this
    option acceptable: the SI-03 warning is still emitted, non-fatal, carrying
    the artifact name, so `summarize_proposed` can still count and name them.
    """
    from seldon.paper.build import summarize_proposed

    artifacts = {
        "result:a": _node("a", state="proposed", value=1.0),
        "result:b": _node("b", state="proposed", value=2.0),
    }

    resolved, errors = resolve_references(
        "{{result:a:value}} {{result:a:value}} {{result:b:value}}",
        artifacts,
        "test.md",
        allow_proposed=True,
        mark_proposed=False,
    )

    assert resolved == "1.0 1.0 2.0"
    assert [e.check_id for e in errors] == ["SI-03", "SI-03", "SI-03"]
    assert all(e.fatal is False for e in errors)
    assert summarize_proposed(errors) == (3, ["a", "b"])
    # The warning says what actually happened to the text.
    assert "without a marker" in errors[0].message


def test_mark_proposed_defaults_to_true():
    """Existing callers see exactly today's output."""
    artifacts = {"result:rate": _node("rate", state="proposed", value=7.5)}

    resolved, errors = resolve_references(
        "{{result:rate:value}}", artifacts, "test.md", allow_proposed=True
    )

    assert resolved == f"7.5 {PROPOSED_MARKER}"
    assert errors[0].fatal is False


def test_mark_proposed_false_does_not_admit_a_proposed_result_on_its_own():
    """mark_proposed governs rendering only; allow_proposed still gates entry."""
    artifacts = {"result:rate": _node("rate", state="proposed", value=7.5)}

    resolved, errors = resolve_references(
        "{{result:rate:value}}", artifacts, "test.md", mark_proposed=False
    )

    assert resolved == "{{result:rate:value}}"
    assert [e.check_id for e in errors] == ["SI-03"]
    assert errors[0].fatal is True


def test_mark_proposed_false_leaves_verified_results_alone():
    artifacts = {
        "result:v": _node("v", value=1.25),
        "result:p": _node("p", state="proposed", value=9.0),
    }

    resolved, _errors = resolve_references(
        "{{result:v:value}} and {{result:p:value}}",
        artifacts,
        "test.md",
        allow_proposed=True,
        mark_proposed=False,
    )

    assert resolved == "1.25 and 9.0"


# ---------------------------------------------------------------------------
# The two together — the shim's whole adaptation layer, expressed as options
# ---------------------------------------------------------------------------

def test_both_options_reproduce_the_shim_output_without_doctoring_the_index():
    """The exact ai-readiness-kg case: proposed Result, integral float, "26"."""
    artifacts = {"result:g1_admitted": _node("g1_admitted", state="proposed",
                                             value=26.0)}

    resolved, errors = resolve_references(
        "The gate admitted {{result:g1_admitted:value}} documents.",
        artifacts,
        "findings.md",
        allow_proposed=True,
        mark_proposed=False,
        value_formatter=_integral_float_formatter,
    )

    assert resolved == "The gate admitted 26 documents."
    assert [e.check_id for e in errors] == ["SI-03"]
    assert errors[0].fatal is False
    assert errors[0].artifact_name == "g1_admitted"
    # Neither workaround was needed: the node is untouched.
    assert artifacts["result:g1_admitted"] == _node(
        "g1_admitted", state="proposed", value=26.0
    )


def test_proposed_marker_still_follows_the_formatted_value():
    """value_formatter and the marker compose; the marker is not bypassed."""
    artifacts = {"result:count": _node("count", state="proposed", value=26.0)}

    resolved, _errors = resolve_references(
        "{{result:count:value}}",
        artifacts,
        "test.md",
        allow_proposed=True,
        value_formatter=_integral_float_formatter,
    )

    assert resolved == f"26 {PROPOSED_MARKER}"
