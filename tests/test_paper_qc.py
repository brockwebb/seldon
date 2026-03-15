"""
Comprehensive unit tests for seldon.paper.qc
"""

import pytest
from seldon.paper.qc import (
    Violation,
    _strip_skipped_regions,
    _split_sentences,
    _split_paragraphs,
    check_PQ_01,
    check_PQ_02,
    check_PQ_03,
    check_PQ_04,
    check_PQ_05,
    check_PQ_06,
    check_PQ_07,
    check_SP_01,
    check_SP_02,
    check_SP_03,
    check_SP_04,
    check_SP_05,
    check_SP_06,
    run_tier2,
    run_tier3,
    load_qc_config,
    load_style_config,
    format_violations,
)

# ---------------------------------------------------------------------------
# Load real configs for integration tests
# ---------------------------------------------------------------------------

QC_CONFIG = load_qc_config()
STYLE_CONFIG = load_style_config()


# ---------------------------------------------------------------------------
# Helper: build a minimal QC config
# ---------------------------------------------------------------------------

def _qc(
    max_sentence_words=35,
    min_paragraph_sentences=2,
    max_paragraph_sentences=8,
    no_semicolons_over_words=20,
):
    return {
        "prose_rules": {
            "max_sentence_words": max_sentence_words,
            "min_paragraph_sentences": min_paragraph_sentences,
            "max_paragraph_sentences": max_paragraph_sentences,
            "no_semicolons_over_words": no_semicolons_over_words,
        }
    }


def _style(
    banned_words=None,
    banned_phrases=None,
    cliche_patterns=None,
    self_congratulation=None,
    nominalizations=None,
    repetition_detection=None,
):
    return {
        "banned_words": banned_words or {"always": [], "paper_specific": []},
        "banned_phrases": banned_phrases or {"always": [], "paper_specific": []},
        "cliche_patterns": cliche_patterns or [],
        "self_congratulation": self_congratulation or {"flag_words": []},
        "nominalizations": nominalizations or {},
        "repetition_detection": repetition_detection or {
            "window_paragraphs": 3,
            "min_word_length": 6,
            "min_occurrences": 3,
            "exclude": [],
        },
    }


# ---------------------------------------------------------------------------
# _strip_skipped_regions
# ---------------------------------------------------------------------------

class TestStripSkippedRegions:
    def test_code_block_whitespace_preserved_lines(self):
        text = "line one\n```\nnovel content\n```\nline two"
        result = _strip_skipped_regions(text)
        assert result.count("\n") == text.count("\n"), "line count must be preserved"
        assert "novel" not in result

    def test_frontmatter_stripped(self):
        text = "---\ntitle: My Novel Paper\ndate: 2024\n---\nActual prose."
        result = _strip_skipped_regions(text)
        assert "novel" not in result.lower()
        assert "Actual prose." in result

    def test_reference_token_stripped(self):
        text = "The value is {{result:foo:value}} as shown."
        result = _strip_skipped_regions(text)
        assert "{{" not in result
        assert "result:foo:value" not in result
        # Original length unchanged
        assert len(result) == len(text)

    def test_normal_text_unchanged(self):
        text = "This is a normal sentence. Nothing to strip."
        result = _strip_skipped_regions(text)
        assert result == text

    def test_code_block_preserves_line_numbers(self):
        # text has 5 lines: line 1 / ``` / code line / ``` / line 4
        text = "line 1\n```\ncode line\n```\nline 4"
        result = _strip_skipped_regions(text)
        result_lines = result.splitlines()
        assert result_lines[0] == "line 1"
        # index 4 (0-based) is "line 4" — indices 1-3 are the fenced block
        assert result_lines[4] == "line 4"

    def test_multiple_code_blocks(self):
        text = "intro\n```\nblock1\n```\nmiddle\n```\nblock2\n```\nend"
        result = _strip_skipped_regions(text)
        assert "block1" not in result
        assert "block2" not in result
        assert "intro" in result
        assert "middle" in result
        assert "end" in result


# ---------------------------------------------------------------------------
# _split_sentences
# ---------------------------------------------------------------------------

class TestSplitSentences:
    def test_basic_split(self):
        sentences = _split_sentences("Hello world. This is a test.")
        assert len(sentences) == 2

    def test_abbreviation_not_split(self):
        sentences = _split_sentences("We tested it vs. the baseline. Results differ.")
        assert len(sentences) == 2

    def test_dr_not_split(self):
        sentences = _split_sentences("Dr. Smith conducted the experiment. It succeeded.")
        assert len(sentences) == 2

    def test_eg_not_split(self):
        sentences = _split_sentences("Common methods, e.g. SVMs, are used. We chose XGBoost.")
        assert len(sentences) == 2

    def test_fig_not_split(self):
        sentences = _split_sentences("As shown in Fig. 3, the curve rises. This is expected.")
        assert len(sentences) == 2

    def test_exclamation(self):
        sentences = _split_sentences("Wow! That is surprising.")
        assert len(sentences) == 2

    def test_question(self):
        sentences = _split_sentences("Why does this happen? We investigate.")
        assert len(sentences) == 2


# ---------------------------------------------------------------------------
# _split_paragraphs
# ---------------------------------------------------------------------------

class TestSplitParagraphs:
    def test_basic_split(self):
        text = "First paragraph.\n\nSecond paragraph."
        paras = _split_paragraphs(text)
        assert len(paras) == 2

    def test_heading_skipped(self):
        text = "# Introduction\n\nFirst paragraph."
        paras = _split_paragraphs(text)
        assert len(paras) == 1

    def test_table_row_skipped(self):
        text = "| col1 | col2 |\n| a | b |\n\nNormal paragraph."
        paras = _split_paragraphs(text)
        assert len(paras) == 1

    def test_code_fence_skipped(self):
        text = "```python\ncode\n```\n\nNormal paragraph."
        paras = _split_paragraphs(text)
        assert len(paras) == 1


# ---------------------------------------------------------------------------
# PQ-01: Sentence length
# ---------------------------------------------------------------------------

class TestPQ01:
    def test_pq01_long_sentence_fires(self):
        # 40-word sentence
        sentence = " ".join(["word"] * 40) + "."
        text = f"This is an intro. {sentence} This is the end."
        violations = check_PQ_01(text.splitlines(), _qc(max_sentence_words=35))
        assert any(v.check_id == "PQ-01" for v in violations)

    def test_pq01_short_sentence_clean(self):
        # 20-word sentence — should not fire
        sentence = " ".join(["word"] * 20) + "."
        text = f"{sentence} Another sentence follows here."
        violations = check_PQ_01(text.splitlines(), _qc(max_sentence_words=35))
        assert not any(v.check_id == "PQ-01" for v in violations)

    def test_pq01_exactly_at_limit_clean(self):
        sentence = " ".join(["word"] * 35) + "."
        text = f"{sentence} Second sentence."
        violations = check_PQ_01(text.splitlines(), _qc(max_sentence_words=35))
        assert not any(v.check_id == "PQ-01" for v in violations)

    def test_pq01_one_over_limit_fires(self):
        sentence = " ".join(["word"] * 36) + "."
        text = f"{sentence} Second sentence."
        violations = check_PQ_01(text.splitlines(), _qc(max_sentence_words=35))
        assert any(v.check_id == "PQ-01" for v in violations)

    def test_pq01_code_block_skipped(self):
        long_sentence = " ".join(["word"] * 40) + "."
        text = f"```\n{long_sentence}\n```\n\nShort sentence. Another short sentence."
        violations = check_PQ_01(text.splitlines(), _qc(max_sentence_words=35))
        assert not any(v.check_id == "PQ-01" for v in violations)

    def test_pq01_line_number_accurate(self):
        text = "Short sentence.\n\nShort again.\n\n" + " ".join(["word"] * 40) + "."
        violations = check_PQ_01(text.splitlines(), _qc(max_sentence_words=35))
        assert violations
        assert violations[0].line == 5


# ---------------------------------------------------------------------------
# PQ-02: Paragraph sentence count
# ---------------------------------------------------------------------------

class TestPQ02:
    def test_pq02_single_sentence_para_fires(self):
        text = "This is a single sentence paragraph."
        violations = check_PQ_02(text.splitlines(), _qc(min_paragraph_sentences=2))
        assert any(v.check_id == "PQ-02" for v in violations)

    def test_pq02_two_sentence_para_clean(self):
        text = "First sentence here. Second sentence here."
        violations = check_PQ_02(text.splitlines(), _qc(min_paragraph_sentences=2))
        assert not any(v.check_id == "PQ-02" for v in violations)

    def test_pq02_too_many_sentences_fires(self):
        sentences = ". ".join([f"Sentence {i}" for i in range(10)]) + "."
        violations = check_PQ_02(text.splitlines() if (text := sentences) else [], _qc(max_paragraph_sentences=8))
        assert any(v.check_id == "PQ-02" for v in violations)

    def test_pq02_heading_not_counted(self):
        # Heading followed by a single sentence — heading itself shouldn't be
        # a "paragraph" that triggers the check.
        text = "# Introduction\n\nOne sentence only."
        violations = check_PQ_02(text.splitlines(), _qc(min_paragraph_sentences=2))
        # The "Introduction" heading should be skipped; only the prose paragraph counts.
        pq02 = [v for v in violations if v.check_id == "PQ-02"]
        assert len(pq02) == 1  # only the single-sentence paragraph fires


# ---------------------------------------------------------------------------
# PQ-03: Inline bold
# ---------------------------------------------------------------------------

class TestPQ03:
    def test_pq03_bold_in_prose_fires(self):
        text = "This is **important** information for the reader."
        violations = check_PQ_03(text.splitlines(), _qc())
        assert any(v.check_id == "PQ-03" for v in violations)

    def test_pq03_bold_in_heading_clean(self):
        text = "# **Bold Heading** Text"
        violations = check_PQ_03(text.splitlines(), _qc())
        assert not any(v.check_id == "PQ-03" for v in violations)

    def test_pq03_bold_in_table_clean(self):
        text = "| **Header** | Value |"
        violations = check_PQ_03(text.splitlines(), _qc())
        assert not any(v.check_id == "PQ-03" for v in violations)

    def test_pq03_no_bold_clean(self):
        text = "This sentence has no bold text at all."
        violations = check_PQ_03(text.splitlines(), _qc())
        assert not any(v.check_id == "PQ-03" for v in violations)

    def test_pq03_italic_not_flagged(self):
        text = "This is *italic* text, not bold."
        violations = check_PQ_03(text.splitlines(), _qc())
        assert not any(v.check_id == "PQ-03" for v in violations)


# ---------------------------------------------------------------------------
# PQ-04: Em dashes
# ---------------------------------------------------------------------------

class TestPQ04:
    def test_pq04_em_dash_fires(self):
        text = "The result — quite surprising — was positive."
        violations = check_PQ_04(text.splitlines(), _qc())
        assert any(v.check_id == "PQ-04" for v in violations)

    def test_pq04_spaced_double_hyphen_fires(self):
        text = "The result -- quite surprising -- was positive."
        violations = check_PQ_04(text.splitlines(), _qc())
        assert any(v.check_id == "PQ-04" for v in violations)

    def test_pq04_regular_hyphen_clean(self):
        text = "This is a well-known method used in practice."
        violations = check_PQ_04(text.splitlines(), _qc())
        assert not any(v.check_id == "PQ-04" for v in violations)

    def test_pq04_line_number_accurate(self):
        text = "Clean line one.\nClean line two.\nThe result — surprising."
        violations = check_PQ_04(text.splitlines(), _qc())
        assert violations
        assert violations[0].line == 3


# ---------------------------------------------------------------------------
# PQ-05: Semicolons in long sentences
# ---------------------------------------------------------------------------

class TestPQ05:
    def test_pq05_semicolon_long_sentence_fires(self):
        # Sentence with semicolon that exceeds 20-word threshold
        # (construct explicitly to guarantee > 20 words)
        sentence = (
            "The model performed well on the training set; "
            "however, the validation data revealed that the approach "
            "does not generalize to out-of-distribution examples."
        )
        assert len(sentence.split()) > 20, "test sentence must exceed 20 words"
        violations = check_PQ_05(sentence.splitlines(), _qc(no_semicolons_over_words=20))
        assert any(v.check_id == "PQ-05" for v in violations)

    def test_pq05_semicolon_short_sentence_clean(self):
        # Short sentence with semicolon, under threshold
        sentence = "He ran; she walked."
        violations = check_PQ_05(sentence.splitlines(), _qc(no_semicolons_over_words=20))
        assert not any(v.check_id == "PQ-05" for v in violations)

    def test_pq05_long_sentence_no_semicolon_clean(self):
        sentence = " ".join(["word"] * 25) + "."
        violations = check_PQ_05(sentence.splitlines(), _qc(no_semicolons_over_words=20))
        assert not any(v.check_id == "PQ-05" for v in violations)


# ---------------------------------------------------------------------------
# PQ-06: Hedge stacking
# ---------------------------------------------------------------------------

class TestPQ06:
    def test_pq06_hedge_stacking_fires(self):
        text = "This may potentially suggest that the model could be improved."
        violations = check_PQ_06(text.splitlines(), _qc())
        assert any(v.check_id == "PQ-06" for v in violations)

    def test_pq06_single_hedge_clean(self):
        text = "This may suggest that the model is improved."
        violations = check_PQ_06(text.splitlines(), _qc())
        assert not any(v.check_id == "PQ-06" for v in violations)

    def test_pq06_no_hedge_clean(self):
        text = "The model achieves superior performance on all benchmarks."
        violations = check_PQ_06(text.splitlines(), _qc())
        assert not any(v.check_id == "PQ-06" for v in violations)

    def test_pq06_two_distinct_hedges_fires(self):
        text = "The results perhaps appears to be significant in certain contexts."
        violations = check_PQ_06(text.splitlines(), _qc())
        assert any(v.check_id == "PQ-06" for v in violations)


# ---------------------------------------------------------------------------
# PQ-07: Ambiguous pronouns
# ---------------------------------------------------------------------------

class TestPQ07:
    def test_pq07_this_is_fires(self):
        text = "This is important for understanding the overall framework."
        violations = check_PQ_07(text.splitlines(), _qc())
        assert any(v.check_id == "PQ-07" for v in violations)

    def test_pq07_it_was_fires(self):
        text = "It was clear that the baseline approach had limitations."
        violations = check_PQ_07(text.splitlines(), _qc())
        assert any(v.check_id == "PQ-07" for v in violations)

    def test_pq07_this_approach_clean(self):
        # "This approach" — no verb immediately after "This"
        text = "This approach provides the best results."
        violations = check_PQ_07(text.splitlines(), _qc())
        # "provides" is in the verbs list, but "This provides" is what fires, not "This approach provides"
        # The regex requires "This" or "It" DIRECTLY followed by the verb.
        assert not any(v.check_id == "PQ-07" for v in violations)

    def test_pq07_demonstrates_fires(self):
        text = "It demonstrates that our method outperforms prior work."
        violations = check_PQ_07(text.splitlines(), _qc())
        assert any(v.check_id == "PQ-07" for v in violations)


# ---------------------------------------------------------------------------
# SP-01: Banned words
# ---------------------------------------------------------------------------

class TestSP01:
    def test_sp01_banned_word_fires(self):
        config = _style(banned_words={"always": ["novel"], "paper_specific": []})
        text = "We propose a novel method for solving this problem."
        violations = check_SP_01(text.splitlines(), config)
        assert any(v.check_id == "SP-01" for v in violations)

    def test_sp01_clean_text(self):
        config = _style(banned_words={"always": ["novel"], "paper_specific": []})
        text = "We propose a new method for solving this problem."
        violations = check_SP_01(text.splitlines(), config)
        assert not any(v.check_id == "SP-01" for v in violations)

    def test_sp01_case_insensitive(self):
        config = _style(banned_words={"always": ["novel"], "paper_specific": []})
        text = "We propose a NOVEL method."
        violations = check_SP_01(text.splitlines(), config)
        assert any(v.check_id == "SP-01" for v in violations)

    def test_sp01_paper_specific_words(self):
        config = _style(banned_words={"always": [], "paper_specific": ["synergy"]})
        text = "There is great synergy between the components."
        violations = check_SP_01(text.splitlines(), config)
        assert any(v.check_id == "SP-01" for v in violations)

    def test_sp01_word_boundary(self):
        # "novels" should not trigger the "novel" ban
        config = _style(banned_words={"always": ["novel"], "paper_specific": []})
        text = "She read novels as a hobby."
        violations = check_SP_01(text.splitlines(), config)
        assert not any(v.check_id == "SP-01" for v in violations)


# ---------------------------------------------------------------------------
# SP-02: Banned phrases
# ---------------------------------------------------------------------------

class TestSP02:
    def test_sp02_banned_phrase_fires(self):
        config = _style(banned_phrases={"always": ["it is important to note"], "paper_specific": []})
        text = "It is important to note that these results are significant."
        violations = check_SP_02(text.splitlines(), config)
        assert any(v.check_id == "SP-02" for v in violations)

    def test_sp02_clean_text(self):
        config = _style(banned_phrases={"always": ["it is important to note"], "paper_specific": []})
        text = "These results demonstrate the effectiveness of our approach."
        violations = check_SP_02(text.splitlines(), config)
        assert not any(v.check_id == "SP-02" for v in violations)

    def test_sp02_case_insensitive(self):
        config = _style(banned_phrases={"always": ["it is important to note"], "paper_specific": []})
        text = "IT IS IMPORTANT TO NOTE that performance improved."
        violations = check_SP_02(text.splitlines(), config)
        assert any(v.check_id == "SP-02" for v in violations)


# ---------------------------------------------------------------------------
# SP-03: Repetition
# ---------------------------------------------------------------------------

class TestSP03:
    def test_sp03_repeated_word_fires(self):
        # "method" repeated 3+ times in 3 paragraphs
        config = _style(repetition_detection={
            "window_paragraphs": 3,
            "min_word_length": 6,
            "min_occurrences": 3,
            "exclude": [],
        })
        text = (
            "The method was first tested.\n\n"
            "Then the method was applied to all cases.\n\n"
            "The method produced good results."
        )
        violations = check_SP_03(text.splitlines(), config)
        assert any(v.check_id == "SP-03" for v in violations)

    def test_sp03_excluded_word_clean(self):
        config = _style(repetition_detection={
            "window_paragraphs": 3,
            "min_word_length": 6,
            "min_occurrences": 3,
            "exclude": ["method"],
        })
        text = (
            "The method was first tested.\n\n"
            "Then the method was applied.\n\n"
            "The method produced results."
        )
        violations = check_SP_03(text.splitlines(), config)
        assert not any(v.check_id == "SP-03" for v in violations)

    def test_sp03_short_words_ignored(self):
        # "the" is short and should not fire
        config = _style(repetition_detection={
            "window_paragraphs": 3,
            "min_word_length": 6,
            "min_occurrences": 3,
            "exclude": [],
        })
        text = (
            "The cat sat.\n\n"
            "The cat ran.\n\n"
            "The cat hid."
        )
        violations = check_SP_03(text.splitlines(), config)
        assert not any(v.check_id == "SP-03" for v in violations)


# ---------------------------------------------------------------------------
# SP-04: Clichés
# ---------------------------------------------------------------------------

class TestSP04:
    def test_sp04_cliche_fires(self):
        config = _style(cliche_patterns=[r"\bpaves the way\b"])
        text = "This research paves the way for future work."
        violations = check_SP_04(text.splitlines(), config)
        assert any(v.check_id == "SP-04" for v in violations)

    def test_sp04_clean_text(self):
        config = _style(cliche_patterns=[r"\bpaves the way\b"])
        text = "This research opens new possibilities for the field."
        violations = check_SP_04(text.splitlines(), config)
        assert not any(v.check_id == "SP-04" for v in violations)

    def test_sp04_case_insensitive(self):
        config = _style(cliche_patterns=[r"\bpaves the way\b"])
        text = "This PAVES THE WAY for progress."
        violations = check_SP_04(text.splitlines(), config)
        assert any(v.check_id == "SP-04" for v in violations)


# ---------------------------------------------------------------------------
# SP-05: Self-congratulation
# ---------------------------------------------------------------------------

class TestSP05:
    def test_sp05_very_fires(self):
        config = _style(self_congratulation={"flag_words": ["very"]})
        text = "The results are very impressive indeed."
        violations = check_SP_05(text.splitlines(), config)
        assert any(v.check_id == "SP-05" for v in violations)

    def test_sp05_clean(self):
        config = _style(self_congratulation={"flag_words": ["very"]})
        text = "The results confirm our hypothesis."
        violations = check_SP_05(text.splitlines(), config)
        assert not any(v.check_id == "SP-05" for v in violations)


# ---------------------------------------------------------------------------
# SP-06: Nominalizations
# ---------------------------------------------------------------------------

class TestSP06:
    def test_sp06_nominalization_fires(self):
        config = _style(nominalizations={"make a decision": "decide"})
        text = "We need to make a decision about the approach."
        violations = check_SP_06(text.splitlines(), config)
        assert any(v.check_id == "SP-06" for v in violations)

    def test_sp06_clean(self):
        config = _style(nominalizations={"make a decision": "decide"})
        text = "We decided to use the new approach."
        violations = check_SP_06(text.splitlines(), config)
        assert not any(v.check_id == "SP-06" for v in violations)

    def test_sp06_message_includes_suggestion(self):
        config = _style(nominalizations={"make a decision": "decide"})
        text = "We need to make a decision."
        violations = check_SP_06(text.splitlines(), config)
        assert violations
        assert "decide" in violations[0].message


# ---------------------------------------------------------------------------
# Code block / frontmatter / reference token skipping
# ---------------------------------------------------------------------------

class TestSkipping:
    def test_code_block_skipped(self):
        # "novel" inside ``` block → does NOT fire SP-01
        config = _style(banned_words={"always": ["novel"], "paper_specific": []})
        text = "Prose before.\n```\nThis is a novel approach.\n```\nProse after."
        violations = check_SP_01(text.splitlines(), config)
        assert not any(v.check_id == "SP-01" for v in violations)

    def test_frontmatter_skipped(self):
        # "novel" inside --- frontmatter → does NOT fire
        config = _style(banned_words={"always": ["novel"], "paper_specific": []})
        text = "---\ntitle: A Novel Approach\ndate: 2024\n---\nActual prose about methods."
        violations = check_SP_01(text.splitlines(), config)
        assert not any(v.check_id == "SP-01" for v in violations)

    def test_reference_token_skipped(self):
        # {{result:foo:value}} → does NOT cause false positive for PQ-04 etc.
        text = "The result is {{result:foo:value}} as expected."
        violations = check_PQ_04(text.splitlines(), _qc())
        assert not any(v.check_id == "PQ-04" for v in violations)

    def test_code_block_long_sentence_skipped(self):
        # Long sentence inside code block should not trigger PQ-01
        long_sentence = " ".join(["word"] * 40) + "."
        text = f"```\n{long_sentence}\n```\n\nShort sentence. Another one here."
        violations = check_PQ_01(text.splitlines(), _qc(max_sentence_words=35))
        assert not any(v.check_id == "PQ-01" for v in violations)

    def test_frontmatter_long_sentence_skipped(self):
        long_sentence = " ".join(["word"] * 40) + "."
        text = f"---\ntitle: {long_sentence}\n---\n\nShort sentence. Another one here."
        violations = check_PQ_01(text.splitlines(), _qc(max_sentence_words=35))
        assert not any(v.check_id == "PQ-01" for v in violations)


# ---------------------------------------------------------------------------
# Integration: run_tier2 and run_tier3
# ---------------------------------------------------------------------------

class TestRunTier2:
    def test_run_tier2_returns_list(self):
        text = "Short. Clean."
        result = run_tier2(text, QC_CONFIG)
        assert isinstance(result, list)

    def test_run_tier2_detects_long_sentence(self):
        sentence = " ".join(["word"] * 40) + "."
        text = f"{sentence} Short second sentence."
        violations = run_tier2(text, QC_CONFIG)
        assert any(v.check_id == "PQ-01" for v in violations)

    def test_run_tier2_detects_em_dash(self):
        text = "The result — surprising — was confirmed."
        violations = run_tier2(text, QC_CONFIG)
        assert any(v.check_id == "PQ-04" for v in violations)

    def test_run_tier2_detects_bold(self):
        text = "This is **very important** prose text."
        violations = run_tier2(text, QC_CONFIG)
        assert any(v.check_id == "PQ-03" for v in violations)


class TestRunTier3:
    def test_run_tier3_returns_list(self):
        text = "Clean prose without issues."
        result = run_tier3(text, STYLE_CONFIG)
        assert isinstance(result, list)

    def test_run_tier3_detects_novel(self):
        text = "We propose a novel method."
        violations = run_tier3(text, STYLE_CONFIG)
        assert any(v.check_id == "SP-01" for v in violations)

    def test_run_tier3_detects_banned_phrase(self):
        text = "It is important to note that the results confirm our approach."
        violations = run_tier3(text, STYLE_CONFIG)
        assert any(v.check_id == "SP-02" for v in violations)


# ---------------------------------------------------------------------------
# format_violations
# ---------------------------------------------------------------------------

class TestFormatViolations:
    def test_format_empty(self):
        output = format_violations([], "TIER 2: Prose Quality")
        assert "No violations" in output

    def test_format_groups_by_check_id(self):
        violations = [
            Violation("PQ-01", "file.md", 1, "Too long", "text"),
            Violation("PQ-01", "file.md", 5, "Too long", "text2"),
            Violation("PQ-03", "file.md", 3, "Bold", "**bold**"),
        ]
        output = format_violations(violations, "TIER 2: Prose Quality")
        assert "PQ-01" in output
        assert "PQ-03" in output
        assert "SUMMARY:" in output

    def test_format_summary_counts(self):
        violations = [
            Violation("PQ-01", "a.md", 1, "Too long", "text"),
            Violation("PQ-04", "b.md", 2, "Em dash", "—"),
        ]
        output = format_violations(violations, "TIER 2: Prose Quality")
        assert "2 violations" in output
        assert "2 files" in output


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

class TestConfigLoading:
    def test_load_qc_config_has_prose_rules(self):
        config = load_qc_config()
        assert "prose_rules" in config
        assert "max_sentence_words" in config["prose_rules"]

    def test_load_style_config_has_banned_words(self):
        config = load_style_config()
        assert "banned_words" in config
        assert "always" in config["banned_words"]
        assert "novel" in config["banned_words"]["always"]

    def test_load_style_config_has_cliche_patterns(self):
        config = load_style_config()
        assert "cliche_patterns" in config
        assert len(config["cliche_patterns"]) > 0


# ---------------------------------------------------------------------------
# Real config integration: spot checks
# ---------------------------------------------------------------------------

class TestRealConfigSpotChecks:
    def test_utilize_banned(self):
        text = "We utilize the entropy-based fitness function."
        violations = run_tier3(text, STYLE_CONFIG)
        assert any(v.check_id == "SP-01" and "utilize" in v.message for v in violations)

    def test_paves_the_way_cliche(self):
        text = "This research paves the way for future work."
        violations = run_tier3(text, STYLE_CONFIG)
        assert any(v.check_id == "SP-04" for v in violations)

    def test_make_a_decision_nominalization(self):
        text = "The committee needs to make a decision about the budget."
        violations = run_tier3(text, STYLE_CONFIG)
        assert any(v.check_id == "SP-06" for v in violations)

    def test_may_potentially_banned_phrase(self):
        text = "The model may potentially improve with more data."
        violations = run_tier3(text, STYLE_CONFIG)
        assert any(v.check_id == "SP-02" for v in violations)
