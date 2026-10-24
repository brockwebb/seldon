# ATTR-001: every governed repository merges its append-only logs by union, the installer writes the attribute, and SQ-021's blocked merge is finished as the measured case

**Repo:** seldon (primary). Cross-repo by absolute path: `/Users/brock/GitHub/squiddy` (writes `.gitattributes`; finishes the kept SQ-021 merge; redrives SQ-036), `/Users/brock/GitHub/arnold`, `/Users/brock/GitHub/ai-readiness-kg`, `/Users/brock/GitHub/hazbrief-mcp` (write `.gitattributes` only, through each repository's hooks). L4: commit and push in all five; the dispatcher merges seldon's branch on green (AD-034 ADDENDUM 01).
**Date:** 2026-10-23. **Authored by:** a Desktop session in squiddy (SQ9).
**Governing:** SEL-004 decision 4 (append-only files merge by git's union driver; the post-merge check reads the result for valid JSONL and unique `event_id`), decision 3 (the dispatcher resolves nothing), AD-034-R8 (one file across worktrees), AD-038-R2 (redrive), DESK-001 (the tool that writes a governed file commits it). Write the fix as AD-034 ADDENDUM 05. No new ruling: decision 4 is applied to the repositories it was never installed in.
**After:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Model:** primary
**Spend:** est. 0.3M tokens. Basis: HOOK-002 (one resolver change, tests, a 130-commit replay) ran under 0.2M est.; this is one installer change with a test, four one-file commits, one hand merge with the gate run, and one redrive. The floor is 131K (AD-037-R11).
**Parts:** A 0.2, B 0.4, C 0.4.
**Network:** none beyond git push.
**Exclusive:** yes
**Premises:**
- premise: seldon declares its append-only logs merge=union | check: `grep -q 'seldon_events.jsonl merge=union' .gitattributes`
- premise: squiddy, arnold, ai-readiness-kg and hazbrief-mcp each carry a seldon_events.jsonl and no such declaration | check: `sh -c 'for r in squiddy arnold ai-readiness-kg hazbrief-mcp; do test -f /Users/brock/GitHub/$r/seldon_events.jsonl || exit 1; test -f /Users/brock/GitHub/$r/.gitattributes && grep -q "merge=union" /Users/brock/GitHub/$r/.gitattributes && exit 1; done; exit 0'`
- premise: the union check and its unique key exist | check: `sh -c 'grep -q "def check_union_text" seldon/core/worktree.py && grep -q "\"union_unique_key\": \"event_id\"" seldon/core/dispatch.py'`
- premise: SQ-021 is blocked on a rebase conflict in seldon_events.jsonl alone, its worktree kept | check: `sh -c 'test -d /Users/brock/GitHub/squiddy/.claude/worktrees/compressed-shimmying-hearth && grep -q "rebase_conflict" /Users/brock/GitHub/squiddy/logs/squiddy_dispatch.log'`
- premise: the installer writes no .gitattributes today | check: `sh -c '! grep -q gitattributes seldon/core/hooks.py'`

Glob and read every sibling `*ATTR-001*ADDENDUM*.md`.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.36M. In Part C, if the union-merged `seldon_events.jsonl` fails `check_union_text` (a fused line or a duplicated `event_id`), stop before fast-forwarding squiddy's main and report the offending lines; do not hand-edit the file.

## The defect, measured

squiddy dispatcher log, 2026-10-23: `MERGE BLOCKED 00203aed (rebase_conflict): seldon_events.jsonl; worktree .claude/worktrees/compressed-shimmying-hearth kept; issue 295ad039`. SQ-021's session finished its work (RESULT on branch `worktree-compressed-shimmying-hearth` at 6f4d784: the standard class adopted on the haiku tier, two classes closed, RFC 8288 admitted end to end), and the dispatcher could not merge it because squiddy's main had gained event lines while the session ran (hazbrief's finding filings and the dispatcher's own records). seldon's `.gitattributes` makes exactly this file `merge=union` (SEL-004 decision 4, with the `event_id` uniqueness check), and no other governed repository has the attribute: `union_files` returns nothing for them, so every worktree session whose project's main moves ends in `rebase_conflict`. The same will happen to SQ-036's redrive and to every future squiddy, arnold and hazbrief dispatch. SQ-019, SQ-023, SQ-028R and SQ-029R merged only because nothing appended to main during them.

## Part A: receipts

`seldon prior-art search`, both arms, logged in the addendum. Named: git's union merge driver (`gitattributes(5)`, `merge=union`, documented for line-oriented append-only files such as changelogs); the `.gitattributes` file as repository state that must be tracked for a driver to apply on a rebase; SEL-004 decision 4 itself (the check that reads the merged result). One line each.

## Part B: the installer writes it, and a project without it is refused

Test first. `seldon hooks install` writes (or extends) the project's `.gitattributes` with the same lines seldon carries for the files that project has (`seldon_events.jsonl`; `governed/ledger/events.jsonl` where `governed/` exists; `state/prior_art_queries.jsonl` where the prior-art block is configured), with the comment naming SEL-004 decision 4, and commits it through the hooks (DESK-001). `seldon dispatch status` reports `union_attribute_missing` for a project whose append-only files are not declared, and the pass refuses launch on it as it refuses c7, naming the files. Then run the installer in squiddy, arnold, ai-readiness-kg and hazbrief-mcp; each gets one commit through its own hooks. hazbrief-mcp has an active Desktop thread: write only `.gitattributes` there and nothing else.

## Part C: SQ-021 finished, SQ-036 redriven

With squiddy's main carrying the attribute: in the kept worktree, `git rebase main`; the union driver merges `seldon_events.jsonl`; run `check_union_text` on the result (valid JSONL, unique `event_id`) and the project's gate (`squiddy/kit.yaml` args under `.venv/bin/python`, as SUITE-001 established); fast-forward main; `seldon cc complete cc_tasks/2026-10-22_SQ-021_extraction_pilot_for_the_ai_readiness_graph_then_its_first_new_document.md` in squiddy; `git worktree remove`; push. Resolve issue 295ad039. Then `seldon dispatch redrive f8433f8c` in squiddy (SQ-036 died on a network failure, `ENOTFOUND`, at 2026-10-23 10:12Z with no code reason; its worktree `ancient-floating-twilight` is kept). Record: lines on each side of the union, lines after, duplicates found (expected 0).

## Deliverables

Code and tests; `docs/design/AD-034_ADDENDUM_05_union_attribute_in_every_governed_repo.md`; the four `.gitattributes` commits; SQ-021 merged and completed; SQ-036 redriven; `cc_tasks/2026-10-23_ATTR-001_every_governed_repo_merges_its_append_only_logs_by_union_RESULT.md` with Part C's counts and premises wrong.
