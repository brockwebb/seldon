"""SEL-047 Part B item 5: the order-dependence check for the tests that passed alone 20 of 20 and failed in a suite
run (iDFlakies, Lam et al. 2019: run the candidate polluters, then the victim, in one process; halve the candidates
on a failure). Each run is one `runs.py extra` line on the ledger. Stops a search after its first failing replay (then
halving starts by hand) or when the search's wall time passes SEARCH_CAP_S.

Candidates are what ran on the victim's xdist worker before it and NOT before it in the alone runs (file order):
- full_n6_3, gw5: test_dispatch_own_record.py's two tests ran first, then the test_dispatch_parallel.py file order.
- full_n6_2, gw0: test_sel008_cross_project_waits_and_block_reason.py ran immediately before the sel018 victim.
"""
import subprocess
import sys
import time

SEARCH_CAP_S = 45 * 60
REPEATS = 3
OWN = ["tests/test_dispatch_own_record.py::test_two_quiet_passes_make_no_commit_and_no_event",
       "tests/test_dispatch_own_record.py::test_a_blocked_cadence_names_the_paths_that_dirty_the_tree"]
PAR = "tests/test_dispatch_parallel.py::"
GW5_PREFIX = OWN + [PAR + t for t in (
    "test_two_disjoint_non_exclusive_tasks_run_concurrently_and_both_merge",
    "test_overlapping_tasks_serialize[overlapping_paths]",
    "test_overlapping_tasks_serialize[two_neo4j_tasks]",
    "test_an_exclusive_task_waits_for_running_ones_and_blocks_new_ones",
    "test_union_merge_of_two_event_appends_is_valid",
    "test_a_duplicate_event_id_in_a_union_file_is_merge_blocked",
    "test_a_conflicting_rebase_ends_merge_blocked_with_an_issue",
    "test_main_moving_under_the_write_set_reruns_the_gate[green]",
    "test_main_moving_under_the_write_set_reruns_the_gate[red]",
    "test_a_killed_supervisor_is_marked_by_the_next_pass_and_its_worktree_kept")]
SEL018 = "tests/test_sel018_relative_dispatch_paths.py::test_dispatch_status_reads_the_cap_from_a_worktree"
SEARCHES = [
    # The gw5 prefix of full_n6_3 replayed in order: both gw5 victims (exclusive_waits at 6, killed_supervisor at 12).
    ("od_gw5_prefix_n6_3", GW5_PREFIX),
    # The sel018 victim alone, then after its gw0 predecessor file.
    ("od_sel018_alone", [SEL018]),
    ("od_sel008_then_sel018", ["tests/test_sel008_cross_project_waits_and_block_reason.py", SEL018]),
]


def failed(name: str) -> bool:
    import json
    for line in open("docs/evidence/sel047/runs.jsonl"):
        r = json.loads(line)
        if r["run"] == name and not r.get("spanned_sleep"):
            return bool(r["failed"] or r["errors"])
    return False


for base, args in SEARCHES:
    t0 = time.monotonic()
    for i in range(1, REPEATS + 1):
        if time.monotonic() - t0 > SEARCH_CAP_S:
            print(f"{base}: search cap {SEARCH_CAP_S} s reached after {i - 1} replay(s)", flush=True)
            break
        name = f"{base}_{i}"
        subprocess.run([sys.executable, "docs/evidence/sel047/scripts/runs.py", "extra", name, *args], check=True)
        if failed(name):
            print(f"{base}: replay {i} failed; stop and halve", flush=True)
            break
