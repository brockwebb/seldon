"""SEL-052 Part B: the returns factory reported (2026-11-26 filing items 1 and the CTAI-008 observation).

1. `seldon cc return` wrote squiddy SQ-143 `**After:**` a consumer filing, which never runs, so the return waited two
   days with nothing saying it would; registration turned the header into a PRECEDES edge. A return now waits on the
   latest open task that can run, and registration refuses an After naming a filing (`after_unrunnable`).
2. critical-thinking-ai CTAI-008, a return, finished green and was `merge_blocked: ungated`: its Part had no check and
   the project declares no gate command. The return template now carries one.
3. A return whose answer says the consumer has nothing to build is completed at filing, with no session.
"""
from __future__ import annotations

import pytest

from seldon.commands.cc import AFTER_UNRUNNABLE, register_task_file
from seldon.core import returns as RT
from tests.test_sel008_cross_project_waits_and_block_reason import (  # noqa: F401  (fixtures)
    OTHER_DB, domain_config, other_db,
)
from tests.test_sel013r_answers_files_its_return import (  # noqa: F401  (fixtures)
    FILING_STEM, TASK_STEM, _answering_task, _config, _file_filing, _git, _invoke, _result, consumer, producer,
)

neo4j_tests = pytest.mark.usefixtures("neo4j_available", "clean_test_db")

KIND_FILING_STEM = "2026-11-24_consumer_filing_from_producer_a_report"


def _kind_filing(consumer, driver, dc) -> str:
    f = consumer / "cc_tasks" / f"{KIND_FILING_STEM}.md"
    f.write_text("# Filing from producer: a report\n\n**Kind:** filing\n**Filed by:** producer\n\nWhat happened.\n",
                 encoding="utf-8")
    return register_task_file(project_dir=consumer, config=_config(consumer), driver=driver, database=OTHER_DB,
                              domain_config=dc, session_id=None, task_path=f, actor="cc",
                              allow_untracked=True)["artifact_id"]


def _state(driver, rel):
    with driver.session(database=OTHER_DB) as s:
        return s.run("MATCH (t:ResearchTask {source_file: $f}) RETURN t.state AS st", f=rel).single()["st"]


def _return_rel(out_text: str) -> str:
    line = next(x for x in out_text.splitlines() if x.startswith("return filed: "))
    return "cc_tasks/" + line.split("/cc_tasks/", 1)[1].split(" ", 1)[0]


@neo4j_tests
def test_a_return_never_waits_on_a_filing(neo4j_driver, producer, consumer, domain_config):
    _file_filing(consumer, neo4j_driver, domain_config)            # an ordinary open task: the one to wait on
    _kind_filing(consumer, neo4j_driver, domain_config)            # registered later, and never runs
    _answering_task(producer, neo4j_driver, domain_config)
    _result(producer)
    filed = _invoke("return", f"cc_tasks/{TASK_STEM}.md", "--to", "consumer")
    assert filed.exit_code == 0, filed.output
    text = (consumer / _return_rel(filed.output)).read_text(encoding="utf-8")
    assert f"**After:** {FILING_STEM}" in text and KIND_FILING_STEM not in text
    # The template's check: a gateless consumer's merge has evidence (AD-034-R26).
    stem = _return_rel(filed.output)[len("cc_tasks/"):-len(".md")]
    assert f"- `check: test -f cc_tasks/{stem}_RESULT.md`" in text


@neo4j_tests
def test_registration_refuses_an_after_that_names_a_filing(neo4j_driver, consumer, domain_config):
    _kind_filing(consumer, neo4j_driver, domain_config)
    f = consumer / "cc_tasks" / "2026-11-26_HB-40_waits_on_a_filing.md"
    f.write_text(f"# HB-40: waits on a filing\n\n**Spend:** zero.\n**Network:** none.\n**After:** {KIND_FILING_STEM}\n"
                 "\n## 1. x\n", encoding="utf-8")
    with pytest.raises(ValueError, match=AFTER_UNRUNNABLE):
        register_task_file(project_dir=consumer, config=_config(consumer), driver=neo4j_driver, database=OTHER_DB,
                           domain_config=domain_config, session_id=None, task_path=f, actor="cc",
                           allow_untracked=True)


NOTHING_RESULT = """# RESULT: SEL-900

Landed the fix in the kit; the consumer's code path is unchanged.

## For consumer

**Nothing to build:** the kit's fix applies on the consumer's next run with no change there; the kit's editable install is read in place.

The fix landed; nothing in this repository changes.
"""


@neo4j_tests
def test_a_return_with_nothing_to_build_is_completed_at_filing(neo4j_driver, producer, consumer, domain_config):
    _file_filing(consumer, neo4j_driver, domain_config)
    _answering_task(producer, neo4j_driver, domain_config)
    _result(producer, NOTHING_RESULT)
    filed = _invoke("return", f"cc_tasks/{TASK_STEM}.md", "--to", "consumer")
    assert filed.exit_code == 0, filed.output
    rel = _return_rel(filed.output)
    text = (consumer / rel).read_text(encoding="utf-8")
    assert "**Nothing to build:** the kit's fix applies" in text and "**After:** none" in text
    assert "check:" not in text
    assert _state(neo4j_driver, rel) == "completed"
    assert "completed at filing: nothing to build" in filed.output
    assert _git(consumer, "status", "--porcelain").stdout == "", "the walk's lines are recorded in the consumer"


@neo4j_tests
def test_a_nothing_to_build_header_with_no_reason_is_refused(neo4j_driver, producer, consumer, domain_config):
    _file_filing(consumer, neo4j_driver, domain_config)
    _answering_task(producer, neo4j_driver, domain_config)
    _result(producer, NOTHING_RESULT.replace("**Nothing to build:** the kit's fix applies on the consumer's next run "
                                             "with no change there; the kit's editable install is read in place.",
                                             "**Nothing to build:**"))
    filed = _invoke("return", f"cc_tasks/{TASK_STEM}.md", "--to", "consumer")
    assert filed.exit_code != 0 and "has no reason" in filed.output, filed.output
    assert not [p for p in (consumer / "cc_tasks").glob("*HB-38*")]
    assert RT.HEADER_NOTHING == "Nothing to build"
