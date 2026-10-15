"""SEL-006 Part C: the `parts_undeclared` gate holds in squiddy, arnold and ai-readiness-kg (Issue f6c69653).

The gate applies to a project once its seldon.yaml names `qc.parts_baseline` (AD-037-R6 c). These read each
project's real seldon.yaml and baseline beside this checkout, and run the function `seldon cc register` calls
(`register_task_file` -> `stations.parts_registration_refusal`) on fixture tasks in a temp directory, so no
project's graph or tree is written. A project that is not checked out beside seldon is skipped, by name.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from seldon.config import load_project_config
from seldon.core import stations

SIBLINGS = Path(__file__).resolve().parents[1].parent
PROJECTS = ["squiddy", "arnold", "ai-readiness-kg"]
UNDECLARED = "# CC Task: fixture\n\n**Implements:** DN-006\n\nNo Parts header.\n"
DECLARED = "# CC Task: fixture\n\n**Implements:** DN-006\n**Parts:** A 0.6, B 0.4.\n\n## Part A: a\n\n## Part B: b\n"


def _project(name: str) -> Path:
    p = SIBLINGS / name
    if not (p / "seldon.yaml").is_file():
        pytest.skip(f"{name} is not checked out beside seldon at {p}")
    return p


@pytest.mark.parametrize("name", PROJECTS)
def test_a_task_without_parts_is_refused(name, tmp_path):
    project = _project(name)
    config = load_project_config(project)
    assert (config.get("qc") or {}).get("parts_baseline"), f"{name}/seldon.yaml names no qc.parts_baseline"
    task = tmp_path / "2026-10-15_fixture.md"
    task.write_text(UNDECLARED)
    refusal = stations.parts_registration_refusal(task, project, config)
    assert refusal and refusal.startswith(stations.PARTS_REFUSAL), refusal
    task.write_text(DECLARED)
    assert stations.parts_registration_refusal(task, project, config) is None


@pytest.mark.parametrize("name", PROJECTS)
def test_a_task_registered_before_the_gate_is_baseline(name):
    project = _project(name)
    config = load_project_config(project)
    listed = sorted(stations.parts_baseline(project, config))
    assert listed, f"{name}'s baseline is empty"
    task = project / listed[0]
    if not task.is_file():
        pytest.skip(f"{listed[0]} is not on disk in {name}")
    assert stations.parts_registration_refusal(task, project, config) is None
