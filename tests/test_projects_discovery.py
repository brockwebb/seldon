"""Cross-project discovery for fleet-wide event-log commands. No Neo4j.

Seldon has no project registry, so a fleet audit has to find projects on disk.
It must do that from configuration — never from a hardcoded home directory.
"""
from __future__ import annotations

import os

import pytest

from seldon.core.projects import (
    PROJECT_ROOTS_ENV_VAR,
    find_projects,
    load_project_ref,
    resolve_projects,
    roots_from_env,
)


def make_project(root, name, database="seldon-x"):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "seldon.yaml").write_text(
        f"project:\n  name: {name}\nneo4j:\n  database: {database}\n"
    )
    return d


def test_load_project_ref_reads_name_and_database(tmp_path):
    d = make_project(tmp_path, "alpha", "seldon-alpha")
    ref = load_project_ref(d)
    assert ref.name == "alpha"
    assert ref.database == "seldon-alpha"
    assert ref.event_log == d.resolve() / "seldon_events.jsonl"
    assert ref.config_error is None


def test_a_broken_config_is_reported_not_raised(tmp_path):
    """A fleet audit must report a broken project, not stop at it."""
    d = tmp_path / "broken"
    d.mkdir()
    (d / "seldon.yaml").write_text("project: [unclosed\n")
    ref = load_project_ref(d)
    assert ref.config_error is not None
    assert ref.database is None


def test_find_projects_walks_to_depth(tmp_path):
    """Projects sit one or two levels below a root, so both must be found."""
    make_project(tmp_path, "a")
    (tmp_path / "nested").mkdir()
    make_project(tmp_path / "nested", "b")
    found = {r.path.name for r in find_projects([tmp_path], depth=3)}
    assert found == {"a", "b"}


def test_find_projects_does_not_descend_into_a_project(tmp_path):
    """A project's subdirectories are part of that project, not new projects."""
    outer = make_project(tmp_path, "outer", "seldon-outer")
    inner = outer / "inner"
    inner.mkdir()
    (inner / "seldon.yaml").write_text("project:\n  name: inner\n")
    found = [r.name for r in find_projects([tmp_path], depth=4)]
    assert found == ["outer"]


def test_find_projects_skips_noise_directories(tmp_path):
    make_project(tmp_path, "node_modules/pkg")
    make_project(tmp_path, ".git/thing")
    assert find_projects([tmp_path], depth=4) == []


def test_find_projects_respects_depth(tmp_path):
    make_project(tmp_path, "a/b/c/d/deep")
    assert find_projects([tmp_path], depth=1) == []


def test_find_projects_ignores_a_missing_root(tmp_path):
    assert find_projects([tmp_path / "nope"]) == []


def test_roots_from_env_splits_on_pathsep(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    env = {PROJECT_ROOTS_ENV_VAR: os.pathsep.join([str(a), str(b), str(tmp_path / "gone")])}
    assert roots_from_env(env) == [a, b]


def test_roots_from_env_is_empty_when_unset():
    assert roots_from_env({}) == []


def test_explicit_project_dirs_suppress_scanning(tmp_path):
    d = make_project(tmp_path, "alpha")
    make_project(tmp_path, "beta")
    refs, notes = resolve_projects(project_dirs=[str(d)], roots=[str(tmp_path)])
    assert [r.name for r in refs] == ["alpha"]
    assert any("explicitly named" in n for n in notes)


def test_explicit_dir_without_a_config_is_reported(tmp_path):
    refs, notes = resolve_projects(project_dirs=[str(tmp_path)])
    assert refs == []
    assert any("no seldon.yaml" in n for n in notes)


def test_roots_option_wins_over_the_environment(tmp_path, monkeypatch):
    a = tmp_path / "fromopt"
    make_project(a, "alpha")
    monkeypatch.setenv(PROJECT_ROOTS_ENV_VAR, str(tmp_path / "fromenv"))
    refs, notes = resolve_projects(roots=[str(a)])
    assert [r.name for r in refs] == ["alpha"]
    assert any("--roots" in n for n in notes)


def test_environment_supplies_the_default_roots(tmp_path, monkeypatch):
    root = tmp_path / "fromenv"
    make_project(root, "alpha")
    monkeypatch.setenv(PROJECT_ROOTS_ENV_VAR, str(root))
    refs, notes = resolve_projects()
    assert [r.name for r in refs] == ["alpha"]
    assert any(PROJECT_ROOTS_ENV_VAR in n for n in notes)


def test_no_roots_falls_back_to_the_current_project_and_says_so(tmp_path, monkeypatch):
    """Silently auditing one project while claiming a fleet sweep would be worse
    than reporting that no roots were configured."""
    d = make_project(tmp_path, "alpha")
    monkeypatch.delenv(PROJECT_ROOTS_ENV_VAR, raising=False)
    monkeypatch.chdir(d)
    refs, notes = resolve_projects()
    assert [r.name for r in refs] == ["alpha"]
    assert any("no roots given" in n for n in notes)


def test_no_roots_and_no_current_project_yields_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv(PROJECT_ROOTS_ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)
    refs, _ = resolve_projects()
    assert refs == []


class TestSeldonYamlIsNotAReservedFilename:
    """A file called `seldon.yaml` is not automatically a Seldon project.

    `webdesktop/services/seldon.yaml` is a *service definition* for a service
    named "seldon" — keys `name`, `subdomain`, `port`, `start_command`, and no
    `project` or `neo4j` section. Matching on filename alone put it into the
    fleet inventory as a project with no database. Harmless in a read-only
    survey; not harmless for anything that iterates the inventory and acts.
    """

    def _write(self, tmp_path, name, body):
        d = tmp_path / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "seldon.yaml").write_text(body)
        return d

    def test_service_definition_is_flagged_not_a_project(self, tmp_path):
        d = self._write(tmp_path, "services", (
            "name: seldon\nsubdomain: seldon\nport: 8765\n"
            "start_command: /usr/bin/python app.py\n"
        ))
        ref = load_project_ref(d)
        assert ref.not_a_project
        assert "not a Seldon project config" in ref.not_a_project
        assert ref.database is None

    def test_a_project_section_alone_is_enough(self, tmp_path):
        d = self._write(tmp_path, "p", "project:\n  name: p\n  domain: research\n")
        assert load_project_ref(d).not_a_project is None

    def test_a_neo4j_section_alone_is_enough(self, tmp_path):
        # A config may name only its database; that is still a Seldon project.
        d = self._write(tmp_path, "p", "neo4j:\n  database: seldon-p\n")
        ref = load_project_ref(d)
        assert ref.not_a_project is None
        assert ref.database == "seldon-p"

    def test_non_mapping_sections_are_a_config_error_not_a_non_project(self, tmp_path):
        # A malformed *Seldon* config must be reported as broken, not quietly
        # dropped from the fleet as "not ours".
        d = self._write(tmp_path, "p", "project: 'a string'\n")
        ref = load_project_ref(d)
        assert ref.config_error
        assert ref.not_a_project is None
