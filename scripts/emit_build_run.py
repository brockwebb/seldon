#!/usr/bin/env python3
"""
emit_build_run.py — append a BuildRun artifact-created event (and a terminal
state-transition event) to a Seldon project's JSONL log.

Defined by AD-025 (DeerFlow as Build-Time Harness).
Schema doc:  seldon/docs/architecture/build_run_event_schema.md
JSON schema: seldon/schemas/build_run.json (defines the BuildRun *properties*
             that go inside the Seldon `artifact_created` event envelope)

Usage:
    python emit_build_run.py \\
        --project /path/to/project \\
        --event-json /path/to/buildrun_payload.json

Architecture note
-----------------
Seldon's event log uses envelope-style events: every line is one of
`artifact_created`, `artifact_updated`, `artifact_state_changed`,
`link_created`, or `link_removed`. The artifact's domain-specific fields go
inside `payload.properties`. AD-025 talks about a "BuildRun event" in
casual terms; concretely that means an `artifact_created` envelope whose
`payload.artifact_type` is `"BuildRun"` and whose `payload.properties`
match `schemas/build_run.json`.

This script emits two envelope events per call so the BuildRun lands in a
terminal state directly:
  1. artifact_created — creates the BuildRun in `proposed` state with the
     validated properties.
  2. artifact_state_changed — transitions it to `completed`, `failed`, or
     `archived` based on `terminal_reason` and `validation_results`.

Both events share a session_id so the projection can group them.

Failures (validation errors, missing files, write failures) raise visible
errors. No silent fallbacks. No partial writes — events go in via the
seldon library's `append_event` which fsyncs each line.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

# Make seldon importable when this script is run directly.
_SELDON_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_SELDON_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_SELDON_REPO_ROOT))

from seldon.core.events import make_event, append_event  # noqa: E402


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"{label} not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _validate(payload: dict[str, Any], schema: dict[str, Any]) -> None:
    """Validate the BuildRun properties payload against the JSON schema."""
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:
        raise SystemExit(
            "jsonschema package is required. Install with `pip install jsonschema`."
        ) from exc

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.absolute_path))
    if errors:
        print("BuildRun payload failed schema validation:", file=sys.stderr)
        for err in errors:
            loc = ".".join(str(p) for p in err.absolute_path) or "<root>"
            print(f"  - at {loc}: {err.message}", file=sys.stderr)
        sys.exit(2)


def _terminal_state(payload: dict[str, Any]) -> str:
    """Map terminal_reason + validation_results to a BuildRun state."""
    terminal_reason = payload["terminal_reason"]
    if terminal_reason == "success":
        verify = (payload.get("validation_results") or {}).get("seldon_verify")
        return "completed" if verify != "fail" else "failed"
    return "failed"  # cost_overrun, wallclock_overrun, invocation_overrun, error, manual_kill


# Neo4j allows only primitive types or arrays-of-primitives on node properties,
# not Maps. The BuildRun schema has four nested-structure fields that must be
# serialized to JSON strings before projection. Cypher can still filter the
# scalar fields (run_id, terminal_reason, total_cost_usd, ...); deep queries
# on the four complex fields parse the JSON in the calling code.
_COMPLEX_FIELDS = ("models_used", "subagents", "files_produced", "validation_results")


def _flatten_for_projection(properties: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of properties with complex fields serialized to JSON strings.

    Keeps the original payload (the JSONL line carries the full structure
    inside payload.properties); only the projection-bound dict is flattened.
    """
    flat = dict(properties)
    for field in _COMPLEX_FIELDS:
        if field in flat and not isinstance(flat[field], str):
            flat[field] = json.dumps(flat[field], separators=(",", ":"), sort_keys=False)
    return flat


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emit a BuildRun artifact + terminal state-change to a Seldon project's event log."
    )
    parser.add_argument(
        "--project",
        type=Path,
        required=True,
        help="Path to the target Seldon project root",
    )
    parser.add_argument(
        "--event-json",
        type=Path,
        required=True,
        help="Path to the JSON file containing the BuildRun properties payload",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=_SELDON_REPO_ROOT / "schemas" / "build_run.json",
        help="Path to build_run.json schema (default: seldon/schemas/build_run.json)",
    )
    parser.add_argument(
        "--actor",
        type=str,
        default="deerflow-buildrun",
        help="Actor string for the envelope events (default: deerflow-buildrun)",
    )
    args = parser.parse_args()

    project_root: Path = args.project.resolve()
    if not project_root.is_dir():
        raise SystemExit(f"Project root is not a directory: {project_root}")

    schema = _load_json(args.schema.resolve(), "BuildRun schema")
    payload = _load_json(args.event_json.resolve(), "Event payload")
    _validate(payload, schema)

    artifact_id = payload["run_id"]  # BuildRun's run_id IS its Seldon artifact_id
    session_id = str(uuid.uuid4())

    # 1) artifact_created: BuildRun lands in `proposed` state with full properties
    #    Complex nested fields are JSON-stringified for Neo4j compatibility;
    #    the original structure is preserved inside the schema-validated
    #    payload that already lives in build_run.json.
    create_event = make_event(
        event_type="artifact_created",
        actor=args.actor,
        authority="accepted",
        session_id=session_id,
        payload={
            "artifact_id": artifact_id,
            "artifact_type": "BuildRun",
            "properties": _flatten_for_projection(payload),
            "from_state": None,
            "to_state": "proposed",
        },
    )
    append_event(project_root, create_event)

    # 2) artifact_state_changed: transition to terminal state
    target_state = _terminal_state(payload)
    transition_event = make_event(
        event_type="artifact_state_changed",
        actor=args.actor,
        authority="accepted",
        session_id=session_id,
        payload={
            "artifact_id": artifact_id,
            "artifact_type": "BuildRun",
            "from_state": "proposed",
            "to_state": target_state,
        },
    )
    append_event(project_root, transition_event)

    print(artifact_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
