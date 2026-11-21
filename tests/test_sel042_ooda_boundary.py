"""SEL-042 ADDENDUM 01 (AD-038-R31): the OODA knowledge source runs nothing outside its worktree.

At 23:01:36Z on 2026-11-20 the OODA session seldon's dispatcher launched in hazbrief-mcp on HB-212 ran
`cd ../../../../seldon && uv run --quiet python -c ...` to check an addendum it had written; `uv run` locked and synced
seldon as a uv project, writing `uv.lock` and `.venv/` into seldon's primary checkout, and the untracked `uv.lock`
refused seldon's queue on c7 (`docs/evidence/sel042/uv_lock_writer.md`). Its prompt forbade commits, pushes and writing
`seldon` commands, and said nothing about other repositories. It now does.
"""
from __future__ import annotations

from seldon.core import ooda


def _brief() -> dict:
    return {"predecessor": {"task_id": "f44dd32b-0000-0000-0000-000000000000",
                            "file": "cc_tasks/2026-11-20_HB-212_benchmark_status_by_significance.md"},
            "result": "cc_tasks/2026-11-20_HB-212_benchmark_status_by_significance_RESULT.md", "result_exists": True,
            "successors": [{"task_id": "abcdef12", "file": "cc_tasks/2026-11-20_HB-213_public_package_build.md",
                            "addenda": [], "governing": [], "premises": [],
                            "addendum_prefix": "cc_tasks/2026-11-20_HB-213_public_package_build_ADDENDUM_02_"}],
            "recall": [], "recall_note": None}


def test_the_prompt_keeps_every_command_inside_the_worktree():
    text = ooda.prompt(_brief())
    assert ooda.BOUNDARY_RULE in text
    for words in ("never change into another repository", "`uv`", "`pip`", "AD-038-R31"):
        assert words in ooda.BOUNDARY_RULE, words


def test_the_rule_comes_before_the_first_step():
    text = ooda.prompt(_brief())
    assert text.index(ooda.BOUNDARY_RULE) < text.index("1. Run `seldon go --brief`.")
