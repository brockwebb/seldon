"""
Pure unit tests for the project-template loader — no Neo4j needed.

Templates live in `seldon/templates/*.yaml` and define the bootstrap state
for a new `seldon init` run. Templates are data, not code: adding a new
project type does not require modifying Python source.
"""
from __future__ import annotations

import pytest

from seldon.templates import loader


class TestListTemplates:
    def test_blank_and_paper_are_shipped(self):
        names = set(loader.list_templates())
        assert "blank" in names
        assert "paper" in names

    def test_returned_names_are_stable_sorted(self):
        names = loader.list_templates()
        assert names == sorted(names)


class TestLoadTemplate:
    def test_blank_has_no_bootstrap_tasks(self):
        tpl = loader.load_template("blank")
        assert tpl["name"] == "blank"
        assert tpl["bootstrap_tasks"] == []

    def test_paper_has_five_setup_tasks(self):
        tpl = loader.load_template("paper")
        assert tpl["name"] == "paper"
        tasks = tpl["bootstrap_tasks"]
        assert len(tasks) == 5
        prefixes = [t["description"].split(":")[0] for t in tasks]
        assert prefixes == ["SETUP-01", "SETUP-02", "SETUP-03", "SETUP-04", "SETUP-05"]

    def test_paper_task_topics_present(self):
        combined = " ".join(
            t["description"].lower()
            for t in loader.load_template("paper")["bootstrap_tasks"]
        )
        for topic in ("bib", "structure", "pipeline", "deploy", "artifact"):
            assert topic in combined

    def test_unknown_template_raises(self):
        with pytest.raises(loader.TemplateNotFoundError) as exc:
            loader.load_template("nonexistent-template-xyz")
        msg = str(exc.value)
        assert "nonexistent-template-xyz" in msg
        # Should hint at available templates so the user can self-correct.
        assert "blank" in msg or "paper" in msg

    def test_each_task_has_description(self):
        for tpl_name in loader.list_templates():
            tpl = loader.load_template(tpl_name)
            for task in tpl["bootstrap_tasks"]:
                assert "description" in task
                assert task["description"].strip(), f"empty description in {tpl_name}"

    def test_template_has_human_readable_description(self):
        for tpl_name in loader.list_templates():
            tpl = loader.load_template(tpl_name)
            assert tpl.get("description", "").strip(), (
                f"template {tpl_name} missing human-readable description"
            )


class TestTemplateValidation:
    def test_missing_name_field_rejected(self, tmp_path, monkeypatch):
        bad = tmp_path / "bad.yaml"
        bad.write_text("bootstrap_tasks: []\n")
        monkeypatch.setattr(loader, "_template_dir", lambda: tmp_path)
        with pytest.raises(loader.TemplateValidationError):
            loader.load_template("bad")

    def test_missing_bootstrap_tasks_field_rejected(self, tmp_path, monkeypatch):
        bad = tmp_path / "bad.yaml"
        bad.write_text("name: bad\ndescription: x\n")
        monkeypatch.setattr(loader, "_template_dir", lambda: tmp_path)
        with pytest.raises(loader.TemplateValidationError):
            loader.load_template("bad")

    def test_bootstrap_task_without_description_rejected(self, tmp_path, monkeypatch):
        bad = tmp_path / "bad.yaml"
        bad.write_text(
            "name: bad\ndescription: x\nbootstrap_tasks:\n  - {}\n"
        )
        monkeypatch.setattr(loader, "_template_dir", lambda: tmp_path)
        with pytest.raises(loader.TemplateValidationError):
            loader.load_template("bad")
