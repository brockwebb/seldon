"""
Tests for check_glossary() path resolution in seldon verify.

No Neo4j needed — pure filesystem tests.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from seldon.commands.verify import _find_glossary, check_glossary
from seldon.paper.glossary_check import (
    find_vocabulary_rule_files,
    load_vocabulary_rules,
    run_glossary_check,
    scan_section,
)


# ---------------------------------------------------------------------------
# Backward-compat: local glossary.md path
# ---------------------------------------------------------------------------

def test_glossary_no_file_warns(tmp_path):
    """No glossary anywhere and no shared_ontology — warn with remediation hint."""
    result = check_glossary(tmp_path)
    assert result.symbol == "warn"
    assert "No shared_ontology" in result.summary


def test_glossary_finds_paper_glossary(tmp_path):
    """Falls back to paper/glossary.md when no config and no check script."""
    glossary = tmp_path / "paper" / "glossary.md"
    glossary.parent.mkdir(parents=True)
    glossary.write_text("# Glossary\n")
    # No check script — skips gracefully, still a pass
    result = check_glossary(tmp_path)
    assert result.symbol == "pass"
    assert "No check_glossary.py found" in result.summary


def test_glossary_finds_book_glossary(tmp_path):
    """Finds book/glossary.md when paper/glossary.md doesn't exist."""
    glossary = tmp_path / "book" / "glossary.md"
    glossary.parent.mkdir(parents=True)
    glossary.write_text("# Glossary\n")
    result = check_glossary(tmp_path)
    assert result.symbol == "pass"
    assert "No check_glossary.py found" in result.summary


def test_glossary_config_book_path_takes_priority(tmp_path):
    """Config 'book' key is checked before conventional fallbacks."""
    custom_dir = tmp_path / "chapters"
    custom_dir.mkdir()
    glossary = custom_dir / "glossary.md"
    glossary.write_text("# Glossary\n")

    config = {"paths": {"book": "chapters"}}
    found = _find_glossary(tmp_path, config)
    assert found == glossary


def test_glossary_config_paper_key(tmp_path):
    """Config 'paper' key resolves correctly."""
    paper_dir = tmp_path / "content"
    paper_dir.mkdir()
    glossary = paper_dir / "glossary.md"
    glossary.write_text("# Glossary\n")

    config = {"paths": {"paper": "content"}}
    found = _find_glossary(tmp_path, config)
    assert found == glossary


def test_find_glossary_returns_none_when_no_file(tmp_path):
    """_find_glossary returns None when no glossary exists anywhere."""
    assert _find_glossary(tmp_path) is None


def test_find_glossary_config_path_not_found_falls_back(tmp_path):
    """Config path pointing to non-existent dir falls through to conventional location."""
    paper_dir = tmp_path / "paper"
    paper_dir.mkdir()
    glossary = paper_dir / "glossary.md"
    glossary.write_text("# Glossary\n")

    # Config specifies a path that doesn't have a glossary
    config = {"paths": {"book": "nonexistent"}}
    found = _find_glossary(tmp_path, config)
    # Falls back to paper/glossary.md
    assert found == glossary


# ---------------------------------------------------------------------------
# Shared ontology path
# ---------------------------------------------------------------------------

def _make_rule_file(directory: Path, rules: dict) -> Path:
    """Write a vocabulary_rules.yaml to directory and return its path."""
    directory.mkdir(parents=True, exist_ok=True)
    rule_path = directory / "vocabulary_rules.yaml"
    rule_path.write_text(yaml.dump({"rules": rules}), encoding="utf-8")
    return rule_path


def test_shared_ontology_no_rule_file_warns(tmp_path):
    """shared_ontology configured but vocabulary_rules.yaml missing → warn."""
    vocab = tmp_path / "ontology" / "validity.md"
    vocab.parent.mkdir(parents=True)
    vocab.write_text("# Vocab\n")
    config = {
        "shared_ontology": {
            "source": str(tmp_path / "ontology"),
            "vocabularies": ["validity.md"],
        }
    }
    result = check_glossary(tmp_path, config)
    assert result.symbol == "warn"
    assert "vocabulary_rules.yaml" in result.summary


def test_shared_ontology_clean_pass(tmp_path):
    """shared_ontology configured with rules, no violations → pass."""
    ontology_dir = tmp_path / "ontology"
    _make_rule_file(ontology_dir, {
        "Confabulation": {
            "banned": [{"phrase": "hallucination", "reason": "use confabulation"}],
            "exemptions": [],
        }
    })
    vocab = ontology_dir / "vocab.md"
    vocab.write_text("# Vocab\n**Confabulation**\n: The generation of false outputs.\n")

    sections_dir = tmp_path / "paper" / "sections"
    sections_dir.mkdir(parents=True)
    (sections_dir / "01_intro.md").write_text("We study confabulation in AI systems.\n")

    config = {
        "shared_ontology": {
            "source": str(ontology_dir),
            "vocabularies": ["vocab.md"],
        }
    }
    result = check_glossary(tmp_path, config)
    assert result.symbol == "pass"
    assert "ontology" in result.summary


def test_shared_ontology_detects_violation(tmp_path):
    """shared_ontology configured, section uses banned synonym → fail."""
    ontology_dir = tmp_path / "ontology"
    _make_rule_file(ontology_dir, {
        "Confabulation": {
            "banned": [{"phrase": "hallucination", "reason": "use confabulation"}],
            "exemptions": [],
        }
    })
    vocab = ontology_dir / "vocab.md"
    vocab.write_text("# Vocab\n")

    sections_dir = tmp_path / "paper" / "sections"
    sections_dir.mkdir(parents=True)
    (sections_dir / "01_intro.md").write_text("The model suffers from hallucination.\n")

    config = {
        "shared_ontology": {
            "source": str(ontology_dir),
            "vocabularies": ["vocab.md"],
        }
    }
    result = check_glossary(tmp_path, config)
    assert result.symbol == "fail"
    assert "1 violation" in result.summary
    assert any("hallucination" in d for d in result.details)


def test_shared_ontology_exemption_suppresses_violation(tmp_path):
    """Exemption context on the same line suppresses the violation."""
    ontology_dir = tmp_path / "ontology"
    _make_rule_file(ontology_dir, {
        "Confabulation": {
            "banned": [{"phrase": "hallucination", "reason": "use confabulation"}],
            "exemptions": ["industry uses the term hallucination"],
        }
    })
    vocab = ontology_dir / "vocab.md"
    vocab.write_text("# Vocab\n")

    sections_dir = tmp_path / "paper" / "sections"
    sections_dir.mkdir(parents=True)
    (sections_dir / "01_intro.md").write_text(
        "Industry uses the term hallucination, but we prefer confabulation.\n"
    )

    config = {
        "shared_ontology": {
            "source": str(ontology_dir),
            "vocabularies": ["vocab.md"],
        }
    }
    result = check_glossary(tmp_path, config)
    assert result.symbol == "pass"


# ---------------------------------------------------------------------------
# glossary_check module unit tests
# ---------------------------------------------------------------------------

def test_load_vocabulary_rules_basic(tmp_path):
    """load_vocabulary_rules returns correct terms, banned, exemptions."""
    rule_path = _make_rule_file(tmp_path, {
        "Context window": {
            "banned": [
                {"phrase": "context buffer", "reason": "not standard"},
                {"phrase": "memory", "reason": "implies persistence"},
            ],
            "exemptions": ["refers variously"],
        }
    })
    terms, banned, exemptions = load_vocabulary_rules([rule_path])
    assert "Context window" in terms
    assert "context buffer" in banned
    assert banned["context buffer"] == "Context window"
    assert "refers variously" in exemptions.get("context buffer", [])
    assert "refers variously" in exemptions.get("memory", [])


def test_find_vocabulary_rule_files(tmp_path):
    """find_vocabulary_rule_files returns paths only for rules that exist."""
    validity_dir = tmp_path / "validity"
    practitioner_dir = tmp_path / "practitioner"
    validity_dir.mkdir()
    practitioner_dir.mkdir()

    vocab1 = validity_dir / "VALIDITY_VOCABULARY.md"
    vocab2 = practitioner_dir / "PRACTITIONER_VOCABULARY.md"
    vocab1.write_text("# v1\n")
    vocab2.write_text("# v2\n")
    # Only validity has a companion rule file
    (validity_dir / "vocabulary_rules.yaml").write_text("rules: {}\n")

    result = find_vocabulary_rule_files([vocab1, vocab2])
    assert len(result) == 1
    assert result[0] == validity_dir / "vocabulary_rules.yaml"


def test_scan_section_whole_word_match(tmp_path):
    """scan_section matches whole words, not substrings."""
    rule_path = _make_rule_file(tmp_path, {
        "Memory": {
            "banned": [{"phrase": "memory", "reason": ""}],
            "exemptions": [],
        }
    })
    terms, banned, exemptions = load_vocabulary_rules([rule_path])
    section = tmp_path / "section.md"
    section.write_text("The system has good memory.\nIn-memory cache is not memory.\n")
    found, violations = scan_section(section, terms, banned, exemptions)
    # "memory" appears twice (whole word match)
    assert len(violations) == 2


def test_run_glossary_check_writes_index(tmp_path):
    """run_glossary_check writes keyword_index.md when index_output_path given."""
    rule_path = _make_rule_file(tmp_path / "ontology", {
        "Confabulation": {
            "banned": [],
            "exemptions": [],
        }
    })
    section = tmp_path / "sections" / "01.md"
    section.parent.mkdir(parents=True)
    section.write_text("We study confabulation here.\n")

    index_out = tmp_path / "keyword_index.md"
    count, messages = run_glossary_check([rule_path], [section], index_out)
    assert count == 0
    assert index_out.exists()
    assert "Confabulation" in index_out.read_text()
