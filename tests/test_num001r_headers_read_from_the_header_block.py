"""NUM-001R Part B: headers are read from the header block only (AD-038-R14).

`cc_tasks/2026-10-27_NUM-001R_task_numbers_allocated_and_headers_read_from_the_header_block.md`.

The block is the preamble: after the `# ` title, up to the first `##` heading or thematic break, fenced code excluded.
A header line starts with a bold label; later fields on such a line are read, except inside backtick code spans. A
header the block carries twice is refused (`header_repeated:<name>`) at registration and at the dispatcher.
"""
from __future__ import annotations

import pytest

from seldon.core import dispatch as D
from tests.test_sel011_registration_refuses_what_dispatch_would_refuse import (  # noqa: F401  (fixtures)
    _dispatch_reason, _register, held, project)

HEADERS = """\
# CC Task — {stem}

**Date:** 2026-10-27
**Framework layer served (DN-005 §5 rule 1):** none.
**Spend:** est. 0.4M tokens.
**Network:** none beyond git push.
**Parts:** A 0.6, B 0.4.
{extra}
## Part A: do the thing.

{body}
"""


def _file(project, stem, extra="", body="Do it."):
    from tests.test_dispatch import _commit
    p = project / "cc_tasks" / f"{stem}.md"
    p.write_text(HEADERS.format(stem=stem, extra=extra, body=body), encoding="utf-8")
    _commit(project, stem)
    return p


# ------------------------------------------------------------------ the reader

def test_a_header_quoted_in_the_body_is_not_read():
    text = HEADERS.format(stem="x", extra="**After:** none",
                          body="A prose line: registration once read **After:** the scan, then the report.\n"
                               "**Network:** under cadence nightly.")
    assert D._header_value(text, "After") == "none"
    assert D._header_value(text, "Network") == "none beyond git push."


def test_a_header_mid_sentence_in_the_block_is_not_a_header_line():
    """2f5d4492: network_kind=cadence was read from a Supersedes sentence."""
    text = ("# T\n\n**Supersedes:** the old file, whose `**Network:** under cadence nightly` line did not parse.\n"
            "Its **After:** was prose too.\n**Spend:** zero model calls.\n")
    assert D._header_value(text, "Network") is None
    assert D._header_value(text, "After") is None
    assert D._header_value(text, "Spend") == "zero model calls."


def test_several_fields_on_one_header_line_are_each_read():
    text = "# T\n\n**Spend:** zero model calls. **Network:** none.\n- **Exclusive:** yes\n"
    assert D._header_value(text, "Network") == "none."
    assert D._header_value(text, "Spend").startswith("zero model calls.")
    assert D.parse_concurrency_headers(text)["Exclusive"] == "yes"


def test_an_empty_header_value_is_continued_by_its_list():
    """squiddy SQ-012/013/015 write `**Spend:**` with the estimate in the list under it."""
    text = "# T\n\n**Spend:**\n- est. 6M tokens for this session;\n- plus Part G's stations.\n**Network:** none.\n"
    assert D.spend_tokens(D._header_value(text, "Spend")) == 6_000_000


def test_a_value_that_opens_with_a_code_span_is_read_whole():
    """Found by the corpus measurement: masking code spans must not skip a value written in backticks."""
    text = "# T\n\n**After:** `2026-10-02_evidence_map_record.md`\n**Touches:** `arnold/` only\n"
    assert D._header_value(text, "After") == "`2026-10-02_evidence_map_record.md`"
    assert D.parse_after(D._header_value(text, "After"))["kind"] == "refs"
    assert D.parse_concurrency_headers(text)["Touches"] == "`arnold/` only"


def test_a_colon_less_label_alone_on_its_line_takes_the_list_under_it():
    """arnold KG-006 writes `**Spend**` and the cap in the list below; the old reader read it, so this one does."""
    text = "# T\n\n**Spend**\n- This task's cap is 2,000,000 tokens, enforced by R-169.\n\n## Steps\n"
    assert D.spend_tokens(D._header_value(text, "Spend")) == 2_000_000


def test_the_block_ends_at_the_first_section_and_skips_fences():
    text = ("# T\n\n```\n**After:** none\n```\n**Spend:** zero.\n\n---\n\n**Network:** none.\n")
    assert D._header_value(text, "After") is None
    assert D._header_value(text, "Spend") == "zero."
    assert D._header_value(text, "Network") is None


def test_a_file_with_no_title_reads_its_block_from_the_first_line():
    assert D._header_value("**Spend:** zero.\n\n## Steps\n**Network:** none.\n", "Spend") == "zero."


# ------------------------------------------------------------------ registration and the dispatcher

def test_control_a_file_quoting_after_in_its_body_registers_with_its_real_after(held):
    """The task's control fixture: before AD-038-R14 the body's quote was read and refused as `after_unresolved`."""
    # The prose quote comes FIRST, as on 2026-09-22: the old reader took the first match anywhere.
    task = _file(held, "quotes_after",
                 extra="Registration refused twice for a prose **After:** the scan, then the report.\n**After:** none",
                 body="Grammar, quoted: `**After:** none` or **After:** the scan, then the report.")
    from tests.test_sel011_registration_refuses_what_dispatch_would_refuse import _config
    from seldon.commands import cc
    assert cc.registration_static_refusal(task, held, _config(held)) is None
    assert D.parse_after(D._header_value(task.read_text(encoding="utf-8"), D.HEADER_AFTER))["kind"] == "none"
    row_reason = _dispatch_reason(held, task)
    assert row_reason is None, row_reason


@pytest.mark.parametrize("extra,name", [
    ("**After:** none\n**After:** 2026-10-26_SEL-011", "After"),
    ("**Network:** none.", "Network"),
    ("**Exclusive:** yes\n- **Exclusive:** no", "Exclusive"),
])
def test_a_header_the_block_carries_twice_is_refused_at_registration_and_at_dispatch(held, extra, name):
    task = _file(held, f"twice_{name.lower()}", extra=extra)
    with pytest.raises(ValueError) as exc:
        _register(held, task)
    assert str(exc.value).startswith(f"{D.HEADER_REPEATED}:{name}: `**{name}:**` appears 2 times"), str(exc.value)
    assert _dispatch_reason(held, task) == f"{D.HEADER_REPEATED}:{name}"


def test_a_header_repeated_only_in_the_body_is_not_a_repeat(held):
    task = _file(held, "body_repeat", body="**Network:** none, said again in prose.")
    from tests.test_sel011_registration_refuses_what_dispatch_would_refuse import _config
    from seldon.commands import cc
    assert cc.registration_static_refusal(task, held, _config(held)) is None
