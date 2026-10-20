"""DISP-003R Part B step 2 (AD-036 ADDENDUM 07, AD-036-R15): a task's governing notes are its `**Governing:**` header.

Registration and the dispatcher's c14 read a task's governing notes through `prior_art.governing_notes`. It took every
`docs/design/` path anywhere in the body, so a task that named the note it repairs (STD-001 on 2026-10-19, DISP-003 on
2026-10-20) was held `governing_unverified` on a note that does not govern it. A path elsewhere in the body is now
text.
"""
from __future__ import annotations

from seldon.core import prior_art as pa
from tests.test_prior_art import _note, proj  # noqa: F401 (fixture)


def _task(proj, governing: str, body: str):
    p = proj["dir"] / "cc_tasks" / "t.md"
    p.parent.mkdir(exist_ok=True)
    p.write_text(f"# T\n\n**Governing:** {governing}\n**Model:** primary\n\n## Work\n\n{body}\n")
    return p


def test_a_task_naming_an_unverified_note_outside_its_governing_header_registers_without_a_hold(proj):  # noqa: F811
    _note(proj, "AD-098_unverified.md", "# AD-098, no verdict\n")
    t = _task(proj, "docs/design/OLD.md (baseline).",
              "- premise: the note this repairs exists | check: `test -f docs/design/AD-098_unverified.md`\n"
              "Repairs `docs/design/AD-098_unverified.md`.")
    assert pa.governing_notes(t.read_text(), proj["dir"], pa.settings(proj["dir"], proj["config"])) \
        == ["docs/design/OLD.md"]
    assert pa.registration_holds(t, proj["dir"], proj["config"]) == []


def test_negative_control_the_same_note_in_the_governing_header_is_held(proj):  # noqa: F811
    _note(proj, "AD-098_unverified.md", "# AD-098, no verdict\n")
    t = _task(proj, "docs/design/AD-098_unverified.md.", "Nothing else.")
    holds = pa.registration_holds(t, proj["dir"], proj["config"])
    assert [h["note"] for h in holds] == ["docs/design/AD-098_unverified.md"]


def test_an_identifier_in_the_governing_header_still_resolves(proj):  # noqa: F811
    _note(proj, "AD-098_unverified.md", "# AD-098, no verdict\n")
    t = _task(proj, "AD-098-R1.", "Nothing else.")
    assert [h["note"] for h in pa.registration_holds(t, proj["dir"], proj["config"])] \
        == ["docs/design/AD-098_unverified.md"]
