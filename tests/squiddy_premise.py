"""squiddy is an environment premise of seldon's gate, not an optional extra (SEL-063, REVIEW-001 F-33).

`seldon.yaml` `project_new.environment_packages` lists squiddy beside seldon: the library arm, the secret scan and the
graph kit are squiddy's. A test that needs it and skips without it lets a gate on a machine without squiddy pass with
that test unrun (the pa002 rebuild test did, through `pytest.importorskip("squiddy.index")`). `require` fails instead,
naming the premise. The one way to excuse it is `SELDON_TESTS_ALLOW_NO_SQUIDDY=1`, set on purpose, so the skip is on
the record: the form `conftest.neo4j_available` uses for the Neo4j tier (`SELDON_TESTS_ALLOW_NEO4J_SKIP`).
"""
from __future__ import annotations

import importlib
import os

import pytest

#: Set to 1 only to excuse the squiddy-backed tests on purpose; nothing on the development machine sets it.
EXCUSE_ENV = "SELDON_TESTS_ALLOW_NO_SQUIDDY"


def require(module: str):
    """Import `module` (a squiddy module) and return it; fail when it cannot be imported, or skip when the excuse is
    set."""
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        reason = (f"{module} cannot be imported ({exc}); squiddy is a declared environment package of this gate "
                  f"(seldon.yaml project_new.environment_packages)")
        if os.getenv(EXCUSE_ENV) == "1":
            pytest.skip(f"{reason} (excused by {EXCUSE_ENV}=1)")
        pytest.fail(f"{reason}. Install it beside seldon, or set {EXCUSE_ENV}=1 only to excuse it on purpose.",
                    pytrace=False)
