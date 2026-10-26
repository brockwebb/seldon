"""SEL-011: registration refuses what dispatch would refuse, and every non-candidate gets a reason line.

`cc_tasks/2026-10-26_SEL-011_registration_refuses_what_dispatch_would_refuse_and_every_non_candidate_gets_a_reason.md`;
ruling AD-038-R12 (`docs/design/AD-038_ADDENDUM_04_registration_runs_the_dispatchers_static_checks.md`).

A. One function, `seldon.core.dispatch.static_checks`, is what `evaluate` and `seldon cc register` both call. Each
   fixture fails exactly one static check; registration must refuse naming the dispatcher's reason code, and the
   dispatcher must refuse the same file on the same code. The registration half runs `register_task_file` with a
   driver of None: the refusal comes before the graph is touched, so nothing is created.
B. `_refusal_lines` (the pass's log and `seldon go`'s last-pass view) carries one line per non-candidate: id, reason
   code, source file, and the grammar under it.
"""
from __future__ import annotations

import pytest
import yaml

from seldon.commands import cc
from seldon.commands import dispatch as S
from seldon.core import dispatch as D
from seldon.core import prior_art
from tests.models_fixture import write_models_home
from tests.test_dispatch import _commit, _row, _seldon_yaml, _task_file, project  # noqa: F401  (fixture)

#: A file that passes every static check under the fixture project's default configuration.
CLEAN = """\
# CC Task — {stem}

**Date:** 2026-10-26
**Framework layer served (DN-005 §5 rule 1):** none.
**Spend:** est. 0.4M tokens.
**Network:** none beyond git push.
**Parts:** A 0.6, B 0.4.
{extra}
## Part A: do the thing.
"""


def _file(project, stem, extra="", **replace):
    text = CLEAN.format(stem=stem, extra=extra)
    for old, new in replace.items():
        line = next(ln for ln in text.splitlines() if ln.startswith(f"**{old}"))
        text = text.replace(line + "\n", new + ("\n" if new else ""))
    p = project / "cc_tasks" / f"{stem}.md"
    p.write_text(text, encoding="utf-8")
    _commit(project, stem)
    return p


@pytest.fixture
def held(project, tmp_path, monkeypatch):
    """The fixture project, opted in to the Parts gate with an empty baseline, with a models home on disk and the
    gates that are not this task's (AD-030-R9's design note, the lock refresh, the prior-art gate) stubbed."""
    monkeypatch.setenv(cc.models.MODELS_HOME_ENV, str(write_models_home(tmp_path)))
    (project / "baseline.txt").write_text("", encoding="utf-8")
    doc = _seldon_yaml(project)
    doc["qc"] = {"parts_baseline": "baseline.txt"}
    (project / "seldon.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    _commit(project, "opt in")
    monkeypatch.setattr(cc, "enforce_design_reference", lambda *a, **k: None)
    monkeypatch.setattr(cc.models, "ensure_fresh", lambda *a, **k: None)
    monkeypatch.setattr(prior_art, "registration_holds", lambda *a, **k: [])
    return project


def _config(project):
    return yaml.safe_load((project / "seldon.yaml").read_text(encoding="utf-8"))


def _register(project, task):
    return cc.register_task_file(project_dir=project, config=_config(project), driver=None, database="none",
                                 domain_config=None, session_id=None, task_path=task)


def _dispatch_reason(project, task):
    """What the dispatcher says about the same file: its not-a-candidate reason, or the refusal of a candidate."""
    cfg = D.load_dispatch_config(project)
    band = D.resolve_standing_band(project, cfg["standing_band_ref"])
    row = D.evaluate(project, _row(project, task), cfg, band, D.tree_state(project), None, {})
    return row["not_a_candidate_reason"] if not row["candidate"] else D.first_refusal_reason(row)


#: (stem, how the file is spoiled, the reason code both paths must name, a fragment of the grammar text).
CASES = [
    ("no_spend", {"Spend": ""}, "no_header:Spend", "a dispatchable task carries each of"),
    ("no_network", {"Network": ""}, "no_header:Network", "re-filed as a new task file"),
    ("no_layer", {"Framework": ""}, f"no_header:{D.HEADER_LAYER}", "candidacy_headers"),
    ("bad_layer", {"Framework": "**Framework layer served (DN-005 §5 rule 1):** the important one."},
     "framework_layer_names_no_layer", "Tier M, O or D"),
    ("bad_spend", {"Spend": "**Spend:** as needed."}, "spend_unreadable", "token count"),
    ("bad_network", {"Network": "**Network:** the usual hosts."}, "network_undeclared", "allowlist:"),
    ("bad_concurrency", {"Parts": "**Parts:** A 0.6, B 0.4.\n**Exclusive:** no"}, "concurrency_undeclared",
     "must declare Touches"),
    ("bad_model", {"Parts": "**Parts:** A 0.6, B 0.4.\n**Model:** claude-opus-5"}, "model_not_in_lock",
     "not in the lock"),
    ("no_parts", {"Parts": ""}, "parts_undeclared", "an addendum cannot supply it"),
    ("bad_parts", {"Parts": "**Parts:** A 0.6, B 0.6."}, "parts_undeclared", "sum to 1.200"),
    ("bad_after", {"Parts": "**Parts:** A 0.6, B 0.4.\n**After:** the scan, then the report"},
     D.AFTER_UNRESOLVED, "not refs"),
]


@pytest.mark.parametrize("stem,spoil,code,grammar", CASES, ids=[c[0] for c in CASES])
def test_registration_refuses_each_static_check_on_the_dispatchers_code(held, stem, spoil, code, grammar):
    task = _file(held, stem, **spoil)
    with pytest.raises(ValueError) as exc:
        _register(held, task)
    assert str(exc.value).startswith(f"{code}: "), str(exc.value)
    assert grammar in str(exc.value) and f"File: cc_tasks/{stem}.md" in str(exc.value)
    assert _dispatch_reason(held, task) == code, "the dispatcher must refuse the same file on the same code"


def test_a_clean_file_passes_both(held):
    task = _file(held, "clean")
    assert cc.registration_static_refusal(task, held, _config(held)) is None
    cfg = D.load_dispatch_config(held)
    band = D.resolve_standing_band(held, cfg["standing_band_ref"])
    row = D.evaluate(held, _row(held, task), cfg, band, D.tree_state(held), None, {})
    assert row["candidate"] and row["eligible"], row


def test_every_failure_is_named_at_once(held):
    """SEL-010 had three wrong headers and learned of them one registration at a time."""
    task = _file(held, "three", Parts="", Spend="**Spend:** as needed.", Framework="")
    refusal = cc.registration_static_refusal(task, held, _config(held))
    for code in (f"no_header:{D.HEADER_LAYER}", "spend_unreadable", "parts_undeclared"):
        assert f"{code}: " in refusal, refusal


def test_a_project_without_a_dispatcher_is_held_only_to_what_registration_always_applied(held):
    """No `dispatch:` block: the headers, Spend, Network and Exclusive/Touches are the dispatcher's and do not apply;
    the Parts gate, the Model lock and the After grammar always did."""
    doc = _config(held)
    del doc["dispatch"]
    task = _file(held, "nodisp", Spend="", Network="", Framework="")
    assert cc.registration_static_refusal(task, held, doc) is None
    task = _file(held, "nodisp_parts", Parts="")
    assert cc.registration_static_refusal(task, held, doc).startswith("parts_undeclared: ")


def test_a_dispatch_block_that_does_not_load_refuses(held):
    doc = _config(held)
    doc["dispatch"]["enabled"] = "yes"
    refusal = cc.registration_static_refusal(_file(held, "x"), held, doc)
    assert refusal.startswith("dispatch_config_unreadable: ") and "enabled" in refusal


def test_the_registration_config_is_not_mutated_by_the_dispatch_loader(held):
    doc = _config(held)
    before = repr(doc)
    cc.registration_static_refusal(_file(held, "y"), held, doc)
    assert repr(doc) == before


def test_the_spend_refusal_is_its_own_reason_at_dispatch(project):
    """c4 used to report an unparseable Spend as `above_band`, which sent its reader to the band."""
    f = _task_file(project, "vague", spend="as needed.")
    _commit(project)
    assert _dispatch_reason(project, f) == "spend_unreadable"
    assert "spend_unreadable" in D.REFUSAL_REASONS


# ══════════════════════════════════════════════════════════════════════════════
# Part B: a reason line for every non-candidate
# ══════════════════════════════════════════════════════════════════════════════

def test_every_non_candidate_gets_a_line_with_its_id_reason_and_file(project):
    """Issue 9965fbed. A pass that printed "nothing eligible (N open, 0 candidates)" now lists N lines."""
    a = _task_file(project, "a", layer="the important one")
    b = project / "cc_tasks" / "b.md"
    b.write_text("# b\n\nno headers here\n", encoding="utf-8")
    _commit(project)
    cfg = D.load_dispatch_config(project)
    band = D.resolve_standing_band(project, cfg["standing_band_ref"])
    rows = [D.evaluate(project, _row(project, f, artifact_id=tid), cfg, band, D.tree_state(project), None, {})
            for f, tid in ((a, "aaaaaaaa-1"), (b, "bbbbbbbb-2"))]
    assert not any(r["candidate"] for r in rows)
    lines = S._refusal_lines(rows, D.tree_state(project))
    heads = [ln for ln in lines if not ln.startswith("      ")]
    assert heads == ["  aaaaaaaa not_a_candidate: framework_layer_names_no_layer  cc_tasks/a.md",
                     f"  bbbbbbbb not_a_candidate: no_header:{','.join(D.REQUIRED_HEADERS)}  cc_tasks/b.md"]
    assert any("Tier M, O or D" in ln for ln in lines), "the grammar is printed under the reason"


def test_a_future_task_and_a_task_with_no_file_still_get_a_line(project):
    rows = [{"task_id": "cccccccc-3", "candidate": False, "not_a_candidate_reason": "future",
             "not_a_candidate_message": None, "source_file": None},
            {"task_id": None, "candidate": False, "not_a_candidate_reason": "no_source_file",
             "source_file": None}]
    assert S._refusal_lines(rows, {}) == ["  cccccccc not_a_candidate: future  ",
                                          "  ? not_a_candidate: no_source_file  "]


def test_the_dispatch_loader_accepts_its_own_output(project):
    """A pass's cadence registers through `register_task_file` with the block the pass already loaded, and
    registration loads it again: a loader that refused its own tuple of headers refused every cadence instance."""
    import copy
    doc = _config(project)
    D.load_dispatch_config(project, doc)
    assert D.load_dispatch_config(project, copy.deepcopy(doc))["candidacy_headers"] == D.REQUIRED_HEADERS
