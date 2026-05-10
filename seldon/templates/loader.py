"""Load and validate project-init templates from ``seldon/templates/*.yaml``.

Templates are data, not code. Adding a new project type is a new YAML file,
not a Python change. The loader validates shape at load time so that `init`
never touches the graph with a malformed template.

Template schema (minimum required keys):

    name: <str>            # must match filename stem
    description: <str>     # one-line human-readable description
    bootstrap_tasks:       # list (may be empty)
      - description: <str>
        name: <str>        # optional

Unrecognized top-level keys are preserved in the returned dict so that future
extensions (directory scaffolding, seldon.yaml overrides, etc.) can be added
without breaking the loader contract.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import yaml


class TemplateNotFoundError(FileNotFoundError):
    """Raised when a template name does not resolve to a YAML file."""


class TemplateValidationError(ValueError):
    """Raised when a template file fails structural validation."""


def _template_dir() -> Path:
    return Path(__file__).parent


def list_templates() -> List[str]:
    """Return template names (filename stems), sorted."""
    return sorted(p.stem for p in _template_dir().glob("*.yaml"))


def load_template(name: str) -> Dict[str, Any]:
    """Load, validate, and return the template named ``name`` as a dict."""
    path = _template_dir() / f"{name}.yaml"
    if not path.exists():
        available = list_templates()
        raise TemplateNotFoundError(
            f"Unknown template: {name!r}. Available templates: "
            f"{', '.join(available) if available else '(none)'}."
        )
    raw = yaml.safe_load(path.read_text()) or {}
    _validate(name, raw)
    return raw


def _validate(name: str, raw: Any) -> None:
    if not isinstance(raw, dict):
        raise TemplateValidationError(
            f"Template {name!r}: top-level YAML must be a mapping."
        )
    for required in ("name", "description", "bootstrap_tasks"):
        if required not in raw:
            raise TemplateValidationError(
                f"Template {name!r}: missing required field {required!r}."
            )
    if not isinstance(raw["bootstrap_tasks"], list):
        raise TemplateValidationError(
            f"Template {name!r}: bootstrap_tasks must be a list."
        )
    for i, task in enumerate(raw["bootstrap_tasks"]):
        if not isinstance(task, dict) or not task.get("description", "").strip():
            raise TemplateValidationError(
                f"Template {name!r}: bootstrap_tasks[{i}] must be a mapping "
                "with a non-empty 'description'."
            )
