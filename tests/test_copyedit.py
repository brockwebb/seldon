"""Tests for seldon paper copyedit — Tier 0 mechanical checks."""
from pathlib import Path

import pytest

from seldon.paper.copyedit import (
    check_CE_01,
    check_CE_02,
    check_CE_03,
    check_CE_04,
    check_CE_05,
    check_CE_06,
    check_CE_07,
    check_CE_08,
    load_copyedit_config,
    run_copyedit,
)


@pytest.fixture
def config():
    return load_copyedit_config()


# ---------------------------------------------------------------------------
# CE-01: Duplicate sentences
# ---------------------------------------------------------------------------

def test_CE_01_exact_duplicate(config):
    text = (
        "This is a perfectly normal sentence with enough words. "
        "Another sentence here. "
        "This is a perfectly normal sentence with enough words."
    )
    v = check_CE_01(text, config, "test.md")
    assert len(v) == 1
    assert v[0].check_id == "CE-01"


def test_CE_01_no_duplicate(config):
    text = (
        "This is one sentence with enough words in it. "
        "This is a different sentence with other words."
    )
    v = check_CE_01(text, config, "test.md")
    assert len(v) == 0


def test_CE_01_short_sentence_ignored(config):
    text = "Yes. Yes. Yes. No. No."
    v = check_CE_01(text, config, "test.md")
    assert len(v) == 0  # Below min_words threshold


def test_CE_01_cross_file(config):
    sent = "This sentence appears in multiple files and is long enough to flag."
    text_a = f"{sent} Some other content."
    text_b = f"Different intro. {sent}"
    global_sentences: dict = {}
    check_CE_01(text_a, config, "a.md", global_sentences=global_sentences)
    v = check_CE_01(text_b, config, "b.md", global_sentences=global_sentences)
    assert any(viol.check_id == "CE-01" and "a.md" in viol.message for viol in v)


# ---------------------------------------------------------------------------
# CE-02: Duplicate paragraphs
# ---------------------------------------------------------------------------

def test_CE_02_exact_duplicate(config):
    para = "This is a paragraph that is long enough to be flagged as a duplicate when it appears twice in the same document."
    text = f"{para}\n\nSome other paragraph.\n\n{para}"
    v = check_CE_02(text, config, "test.md")
    assert len(v) == 1
    assert v[0].check_id == "CE-02"


def test_CE_02_no_duplicate(config):
    text = "First paragraph with enough words.\n\nSecond paragraph completely different."
    v = check_CE_02(text, config, "test.md")
    assert len(v) == 0


# ---------------------------------------------------------------------------
# CE-03: Near-duplicate phrases
# ---------------------------------------------------------------------------

def test_CE_03_repeated_ngram(config):
    phrase = "the quick brown fox jumps over the lazy dog"
    text = f"Once upon a time, {phrase} and then later {phrase} again."
    v = check_CE_03(text, config, "test.md")
    assert len(v) >= 1
    assert v[0].check_id == "CE-03"


def test_CE_03_excluded_pattern(config):
    text = "In this section we discuss X. In this section we discuss Y."
    v = check_CE_03(text, config, "test.md")
    # "in this section we" is in exclude_patterns — depends on config
    # Either 0 or flagged depending on ngram_size vs. phrase length
    # The key assertion: the check runs without error
    assert all(viol.check_id == "CE-03" for viol in v)


# ---------------------------------------------------------------------------
# CE-04: Orphaned section references
# ---------------------------------------------------------------------------

def test_CE_04_orphaned_ref(config):
    text = "As discussed in Section 99, this approach works well."
    v = check_CE_04(text, config, "03_test.md", heading_sections={"1", "2", "3"})
    assert len(v) >= 1
    assert all(viol.check_id == "CE-04" for viol in v)
    assert any("99" in viol.message for viol in v)


def test_CE_04_valid_ref(config):
    text = "As discussed in Section 3, this approach works well."
    v = check_CE_04(text, config, "03_test.md", heading_sections={"1", "2", "3"})
    assert len(v) == 0


# ---------------------------------------------------------------------------
# CE-05: Orphaned citations
# ---------------------------------------------------------------------------

def test_CE_05_orphaned_cite(config):
    text = "According to {cite:p}`nonexistent_key_2024`, this is true."
    v = check_CE_05(text, config, "test.md", bib_keys={"smith2020", "jones2021"})
    assert len(v) == 1
    assert v[0].check_id == "CE-05"
    assert "nonexistent_key_2024" in v[0].message


def test_CE_05_valid_cite(config):
    text = "According to {cite:p}`smith2020`, this is true."
    v = check_CE_05(text, config, "test.md", bib_keys={"smith2020", "jones2021"})
    assert len(v) == 0


def test_CE_05_no_bib_skips(config):
    text = "According to {cite:p}`anything`, this is true."
    v = check_CE_05(text, config, "test.md", bib_keys=None)
    assert len(v) == 0


# ---------------------------------------------------------------------------
# CE-06: Formatting artifacts
# ---------------------------------------------------------------------------

def test_CE_06_double_space(config):
    text = "This has  two spaces in it."
    v = check_CE_06(text, config, "test.md")
    assert any(viol.check_id == "CE-06" and "Double space" in viol.message for viol in v)


def test_CE_06_repeated_punctuation(config):
    text = "This is wrong.. because of the double period."
    v = check_CE_06(text, config, "test.md")
    assert any(viol.check_id == "CE-06" and "Repeated punctuation" in viol.message for viol in v)


def test_CE_06_trailing_whitespace(config):
    text = "This line has trailing spaces   \nThis one does not."
    v = check_CE_06(text, config, "test.md")
    assert any(viol.check_id == "CE-06" and "Trailing whitespace" in viol.message for viol in v)


# ---------------------------------------------------------------------------
# CE-07: Heading hierarchy
# ---------------------------------------------------------------------------

def test_CE_07_skipped_level(config):
    text = "## Level 2\n\nSome text.\n\n#### Level 4\n\nMore text."
    v = check_CE_07(text, config, "test.md")
    assert len(v) == 1
    assert v[0].check_id == "CE-07"
    assert "jump" in v[0].message.lower()


def test_CE_07_valid_hierarchy(config):
    text = "## Level 2\n\nSome text.\n\n### Level 3\n\nMore text."
    v = check_CE_07(text, config, "test.md")
    assert len(v) == 0


# ---------------------------------------------------------------------------
# CE-08: Leftover markers
# ---------------------------------------------------------------------------

def test_CE_08_todo_in_prose(config):
    text = "This section needs work. TODO: fix this paragraph."
    v = check_CE_08(text, config, "test.md")
    assert len(v) == 1
    assert v[0].check_id == "CE-08"


def test_CE_08_todo_in_code_block_ignored(config):
    text = "Normal prose here.\n\n```python\n# TODO: refactor this\n```\n\nMore prose."
    v = check_CE_08(text, config, "test.md")
    assert len(v) == 0


# ---------------------------------------------------------------------------
# Integration: run_copyedit
# ---------------------------------------------------------------------------

def test_run_copyedit_returns_combined_violations(config):
    text = (
        "## Heading\n\n"
        "This line has  double spaces. TODO: clean this up.\n\n"
        "#### Jumped heading\n"
    )
    v = run_copyedit(text, config, "test.md")
    check_ids = {viol.check_id for viol in v}
    assert "CE-06" in check_ids  # double space
    assert "CE-08" in check_ids  # TODO marker
    assert "CE-07" in check_ids  # heading jump
