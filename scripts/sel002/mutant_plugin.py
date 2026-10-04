"""Pytest plugin for SEL-002's mutation controls: removes ONE catching mechanism of the decision
register, named by the SEL002_MUTANT environment variable, before the tests run.

Each planted-control test in tests/test_decision_register.py must FAIL under its mutant: a test
that still passes with the code it guards removed is not guarding anything (mutation testing,
DeMillo, Lipton and Sayward 1978; methodology 7.6: an instrument is positive-controlled before its
verdict is cited). Loaded only by scripts/sel002/mutation_controls.py via `-p`.
"""
from __future__ import annotations

import os


def pytest_configure(config):
    name = os.environ.get("SEL002_MUTANT")
    if not name:
        return
    from seldon.core import decisions as dr
    import seldon.core.sync as sync

    if name == "no_chain_check":
        dr.Register.verify = lambda self: []
    elif name == "no_fork_check":
        orig = dr._require_active

        def lax(u, qid, role):
            rec = u.get(qid)
            if rec is None:
                return orig(u, qid, role)
            return rec
        dr._require_active = lax
    elif name == "no_existence_check":
        orig = dr._require_active

        def lax(u, qid, role):
            if u.get(qid) is None:
                return None
            return orig(u, qid, role)
        dr._require_active = lax
    elif name == "no_label_check":
        dr.labeled_decisions_after_baseline = lambda s: []
    elif name == "no_imports":
        dr.Universe.scope_repos = lambda self: [self.s.repository]
    elif name == "superseded_binds":
        dr.BINDING = None
        orig_bind = dr.bind

        def bind_all(u, text, threshold):
            for repo in u.scope_repos():
                for r in u.records(repo).values():
                    r.status = "accepted"
            return orig_bind(u, text, threshold)
        dr.BINDING = "accepted"
        dr.bind = bind_all
    elif name == "label_not_owned":
        sync.SELDON_OWNED_LABELS = tuple(x for x in sync.SELDON_OWNED_LABELS if x != "Decision")
        import tests.test_decision_register as t
        t.SELDON_OWNED_LABELS = sync.SELDON_OWNED_LABELS
    elif name == "mutates_legacy":
        orig_demote = dr.demote_positional_rulings

        def demote_and_touch(*, project_dir, driver, database, session_id=None):
            from seldon.core.artifacts import update_artifact
            with driver.session(database=database) as s:
                rows = s.run("MATCH (a:Artifact) WHERE a.artifact_type IN "
                             "['ArchitecturalDecision','DesignNote'] RETURN a.artifact_id AS aid").data()
            for r in rows:
                update_artifact(project_dir=project_dir, driver=driver, database=database,
                                artifact_id=r["aid"], properties={"superseded_by_register": True},
                                actor="mutant", authority="accepted")
            return orig_demote(project_dir=project_dir, driver=driver, database=database,
                               session_id=session_id)
        dr.demote_positional_rulings = demote_and_touch
    elif name == "probe_blind_to_verbs":
        import re as _re
        dr.PROBE_AMEND = _re.compile(r"(?!x)x")
    elif name == "probe_ignores_findings":
        orig_probe = dr.conflicts_probe

        def no_findings(u, findings_path, exclusions_path):
            return orig_probe(u, None, exclusions_path)
        dr.conflicts_probe = no_findings
    else:
        raise SystemExit(f"unknown SEL002_MUTANT {name!r}")
