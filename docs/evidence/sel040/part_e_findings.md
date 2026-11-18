# SEL-040 Part E: the two observations, measured before anything changed

Measured 2026-11-17/18 from hazbrief-mcp's tracked event store and RESULTs (read only; nothing written there) and
seldon's event store. Scripts: `/tmp/sel040/hz_numbered.py`, `/tmp/sel040/hz_decision_nodes.py` (read-only scans of
`seldon_events.jsonl`), reproduced below as their findings.

## (1) Eleven register records absent from hazbrief's graph after HB-186

**What HB-187 saw.** Its first `seldon verify` reported 11 decision records not projected (HBD-390, 429, 431, 434,
435 to 441). It ran `seldon decision project` (7 created, 4 updated) and wrote "HB-186's own verify had reported the
projection current, so the graph lost them after HB-186" (HB-187 RESULT, "seldon verify").

**What the record shows.** The graph never had them; nothing lost them.

1. HB-186 accepted its seven rulings and four amendments in its worktree, where `decision accept` writes to
   `docs/decisions/register/pending/` with no seq (LOOP-001, AD-033 ADDENDUM 01). Its RESULT says its `seldon verify`
   ran "with the 11 pending decision records moved aside and put back (they crash it in a worktree)". Pending records
   are not in the chain, so a projection in the worktree had nothing of theirs to project and verify had nothing of
   theirs to miss: "current" was true of the chain without them.
2. HB-186 merged at 2026-11-15T19:52:08Z. The merge's `register_numbered` event maps exactly the eleven:
   HBD-435..441 (`accept`, seq 514..520) and HBD-390, 429, 431, 434 (`amend`, seq 521..524), committed `cb9b3636`.
3. No `artifact_created`/`artifact_updated` for a `decision_register` node of HBD-435..441 exists before
   2026-11-16T04:26:58Z, when session `df3d278e` (HB-187's `decision project`) created the seven and updated the four.
4. `number_merged_register` (LOOP-001) numbered, rendered and committed; it never projected. Every merge that numbered
   records since LOOP-001 left them for the next `verify --fix` or `decision project` by hand; the 21 numbering events
   in hazbrief's store are each such a window.

**Cause: seldon's.** Of the three candidates the task named, it is "a merge that numbered pending records after
projecting": the only projection that could run before numbering ran in the worktree, where the records were pending.
**Fixed:** the merge step projects what it numbered (`dispatch_worktree._project_register`, AD-034-R24), recorded on
`register_numbered.projected`; a failed projection is printed and left for `seldon decision project`, and never undoes
the merge. Test: `tests/test_loop001_register_seq.py::test_the_records_a_merge_numbers_are_projected_into_the_graph`
(failed with `TypeError: number_merged_register() got an unexpected keyword argument 'driver'` before the change).

## (2) The recall index lists hazbrief Issue `0c4232cb` as `seldon:issue-0c4232cb`

**Where recall takes the name from.** `seldon/core/recall.py::_from_events(repo, root, s)`: the repository's name is
the one whose event store the Issue was folded from (`id=f"{repo}:issue-{aid[:8]}"`). hazbrief's recall searches its
own store and each `decisions.repositories` sibling, seldon among them.

**Why it says seldon.** Because the Issue is seldon's. Its only `artifact_created` is in seldon's
`seldon_events.jsonl` (event `755661cb`, 2026-11-16T00:14:33Z, actor `desktop`, session `b67f54dd`, which wrote
nothing else); hazbrief's store holds only four mentions of it (two `dispatch_launched` and one `recall_listed`
prompt blocks, one `recall_used`). Desktop's `claude_desktop_config.json` sets `SELDON_DEFAULT_PROJECT` to
`/Users/brock/Documents/GitHub/seldon` (a symlink to this repository), and `seldon_issue_create` with no
`project_dir` resolves to it (`mcp_server._resolve_project`). The reply ("Created Issue: 0c4232cb...") named no
repository, so the thread had no way to see where it went.

**Cause: seldon's, but not the recall index's.** The index is right; the write tool was silent about where it wrote.
**Fixed:** `seldon_issue_create` and `seldon_task_create` now reply with `project: <name> (<path>)`, and say
"project_dir was not given, so SELDON_DEFAULT_PROJECT chose it" when the default chose (AD-038-R29). Test:
`tests/test_sel040_addendum_files_and_launch_premises.py::test_an_issue_created_without_project_dir_says_the_default_chose_its_repository`.

**Not changed:** Issue `0c4232cb` stays open in seldon's graph. Moving it means writing into hazbrief's graph, which
this task does not do; the return tells hazbrief so, and that the Issue can be re-filed in its own graph with
`project_dir` given, after which seldon's copy is closed as a duplicate by a seldon session.
