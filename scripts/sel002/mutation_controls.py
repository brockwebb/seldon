"""Run each SEL-002 planted control with its catching code removed, and record that it fails.

    python -m dotenv -f .env run -- python scripts/sel002/mutation_controls.py

Writes evidence/sel002/mutation_controls.txt. Exit 0 only when every planted test passes on the
real code AND fails under its mutant. Zero model calls, no network.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "evidence" / "sel002" / "mutation_controls.txt"
TESTS = "tests/test_decision_register.py"

#: planted test -> the mutant that removes the code catching it
CONTROLS = [
    ("test_planted_hand_edited_record_fails_the_check", "no_chain_check"),
    ("test_planted_reformatted_record_with_equal_data_fails_the_check", "no_chain_check"),
    ("test_planted_removed_record_breaks_the_chain", "no_chain_check"),
    ("test_planted_forked_supersession_is_refused_naming_the_live_head", "no_fork_check"),
    ("test_planted_supersession_of_a_missing_id_is_refused_and_writes_nothing", "no_existence_check"),
    ("test_planted_labeled_decision_without_a_record_fails_the_check", "no_label_check"),
    ("test_planted_arnold_registration_resolves_squiddy_r112", "no_imports"),
    ("test_planted_superseded_record_never_binds_the_r29_case", "superseded_binds"),
    ("test_the_decision_label_joins_the_owned_label_set", "label_not_owned"),
    ("test_projection_leaves_legacy_decision_nodes_unchanged", "mutates_legacy"),
    ("test_planted_silent_supersession_is_caught_by_the_probe", "probe_blind_to_verbs"),
    ("test_planted_open_contradiction_is_caught_by_the_probe", "probe_ignores_findings"),
]


def run(test: str, mutant: str | None) -> tuple[int, str]:
    env = dict(os.environ)
    env.pop("SEL002_MUTANT", None)
    if mutant:
        env["SEL002_MUTANT"] = mutant
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    r = subprocess.run([sys.executable, "-m", "pytest", f"{TESTS}::{test}", "-q", "-p",
                        "scripts.sel002.mutant_plugin", "--no-header", "-rN"],
                       cwd=ROOT, env=env, capture_output=True, text=True)
    tail = [ln for ln in (r.stdout + r.stderr).splitlines() if ln.strip()][-1:]
    return r.returncode, " ".join(tail)


def main() -> int:
    lines = ["# SEL-002 mutation controls: each planted test passes on the code and fails without it",
             "", "| planted test | real code | mutant | under mutant |", "|---|---|---|---|"]
    ok = True
    for test, mutant in CONTROLS:
        rc0, t0 = run(test, None)
        rc1, t1 = run(test, mutant)
        good = rc0 == 0 and rc1 != 0
        ok &= good
        lines.append(f"| {test} | {'pass' if rc0 == 0 else 'FAIL'} ({t0}) | {mutant} | "
                     f"{'fails, as it must' if rc1 != 0 else 'STILL PASSES'} ({t1}) |")
        print(lines[-1], flush=True)
    lines += ["", f"verdict: {'every control is load-bearing' if ok else 'A CONTROL GUARDS NOTHING'}"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
