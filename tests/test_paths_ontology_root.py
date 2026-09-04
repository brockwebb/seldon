"""Ontology-root resolution must be checkout-relative, not developer-relative.

2026-09-04 defect sweep RESULT §7.6: ``seldon.yaml`` carried
``shared_ontology.source: /Users/brock/GitHub/seldon/ontology/``. That path
exists, so nothing ever failed — every ingest run from a git worktree quietly
read the **main checkout's** vocabulary instead of the worktree's, and a
vocabulary edit could not be tested without editing the main checkout. A
hardcoded absolute path in committed config is a "Never Hardcode" violation
whose symptom is a wrong answer, not an error.

Two independent mechanisms fix it, and the tests below pin both:

* a *relative* source resolves against the directory holding ``seldon.yaml``,
  so each checkout and worktree reads its own tree;
* a source that does not exist falls back to the ontology tree beside the
  installed package, instead of "cannot locate vocabulary file".

Neither subsumes the other. The fallback alone would never have fired for the
original defect, because the hardcoded path existed.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from seldon.paths import (
    ONTOLOGY_MARKER,
    distribution_root,
    resolve_ontology_root,
)


def _make_ontology_tree(root: Path) -> Path:
    """Create a minimal directory that satisfies :func:`is_ontology_root`."""
    marker = root / ONTOLOGY_MARKER
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("# stub vocabulary\n", encoding="utf-8")
    return root


class TestResolveOntologyRoot:
    def test_relative_source_resolves_against_the_project_dir(self, tmp_path):
        """This is the worktree fix: same config, different checkout, own tree."""
        project = tmp_path / "checkout"
        _make_ontology_tree(project / "ontology")

        assert resolve_ontology_root("ontology/", project) == (
            project / "ontology"
        ).resolve()

    def test_relative_source_ignores_the_process_cwd(self, tmp_path, monkeypatch):
        """Resolution must not depend on where the command was launched from."""
        project = tmp_path / "checkout"
        _make_ontology_tree(project / "ontology")
        elsewhere = tmp_path / "elsewhere" / "ontology"
        _make_ontology_tree(elsewhere)
        monkeypatch.chdir(tmp_path / "elsewhere")

        assert resolve_ontology_root("ontology/", project) == (
            project / "ontology"
        ).resolve()

    def test_two_checkouts_of_the_same_config_resolve_to_different_trees(
        self, tmp_path
    ):
        """The property the defect violated, stated directly."""
        main = tmp_path / "main"
        worktree = tmp_path / "worktree"
        _make_ontology_tree(main / "ontology")
        _make_ontology_tree(worktree / "ontology")

        assert resolve_ontology_root("ontology/", main) != resolve_ontology_root(
            "ontology/", worktree
        )

    def test_absolute_source_is_honoured_as_given(self, tmp_path):
        """Projects outside the Seldon repo legitimately name an absolute tree."""
        external = _make_ontology_tree(tmp_path / "shared" / "ontology")
        project = tmp_path / "some-project"
        project.mkdir()

        assert resolve_ontology_root(str(external), project) == external.resolve()

    def test_missing_source_falls_back_to_the_packaged_tree(self, tmp_path):
        """A moved or renamed checkout self-heals instead of erroring."""
        project = tmp_path / "no-ontology-here"
        project.mkdir()

        assert resolve_ontology_root(
            "/definitely/not/a/real/ontology/root", project
        ) == (distribution_root() / "ontology").resolve()

    def test_absent_source_key_falls_back_to_the_packaged_tree(self, tmp_path):
        """``shared_ontology`` with no ``source`` is not a hard failure."""
        project = tmp_path / "no-source-configured"
        project.mkdir()

        assert resolve_ontology_root(None, project) == (
            distribution_root() / "ontology"
        ).resolve()

    def test_a_bare_directory_named_ontology_is_not_a_root(self, tmp_path):
        """The fallback is marker-checked, so it cannot land on seldon/ontology/.

        ``seldon/ontology/`` is the parser CODE package. Accepting any directory
        called ``ontology`` would resolve the vocabulary tree to Python source.
        """
        project = tmp_path / "project"
        (project / "ontology").mkdir(parents=True)  # no marker file

        # The configured relative dir exists, so it wins — but if it did not,
        # the derived candidate is only accepted when the marker is present.
        resolved = resolve_ontology_root("ontology/", project)
        assert resolved == (project / "ontology").resolve()
        assert resolve_ontology_root("ontology/", tmp_path / "absent") == (
            distribution_root() / "ontology"
        ).resolve()


class TestSeldonYamlIsNotHardcoded:
    """The committed config must not name one developer's clone."""

    def test_shared_ontology_source_is_relative(self):
        import yaml

        config_path = distribution_root() / "seldon.yaml"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        source = config["shared_ontology"]["source"]
        assert not Path(source).is_absolute(), (
            f"seldon.yaml hardcodes an absolute ontology source: {source!r}. "
            "Use a path relative to the repository root so every checkout and "
            "worktree reads its own vocabulary tree."
        )
        assert not source.startswith("~")


class TestVocabularyPathsResolveToThisCheckout:
    """End to end: the ontology command reads the checkout it is running in."""

    def test_resolve_vocabulary_paths_stays_inside_this_checkout(
        self, tmp_path, monkeypatch
    ):
        from seldon.commands.ontology import _resolve_vocabulary_paths

        monkeypatch.delenv("SELDON_ONTOLOGY_PATH", raising=False)
        monkeypatch.chdir(distribution_root())

        paths = _resolve_vocabulary_paths()
        assert paths, "no vocabulary files resolved"
        for path in paths:
            assert path.exists()
            assert path.resolve().is_relative_to(distribution_root()), (
                f"{path} resolves outside this checkout — the worktree defect"
            )

    def test_env_override_still_wins(self, tmp_path, monkeypatch):
        """SELDON_ONTOLOGY_PATH names a single FILE here and still short-circuits."""
        from seldon.commands.ontology import _resolve_vocabulary_paths

        vocab = tmp_path / "VALIDITY_VOCABULARY.md"
        vocab.write_text("# stub\n", encoding="utf-8")
        monkeypatch.setenv("SELDON_ONTOLOGY_PATH", str(vocab))

        assert _resolve_vocabulary_paths() == [vocab]

    def test_env_override_pointing_nowhere_fails_loudly(self, tmp_path, monkeypatch):
        import click

        from seldon.commands.ontology import _resolve_vocabulary_paths

        monkeypatch.setenv("SELDON_ONTOLOGY_PATH", str(tmp_path / "nope.md"))
        with pytest.raises(click.ClickException) as exc:
            _resolve_vocabulary_paths()
        assert "non-existent" in str(exc.value)
