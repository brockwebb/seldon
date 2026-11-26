# Filing from factory: a return task waited on a filing that never runs, a JSON command warns on stdout, the MCP portfolio brief shows one project, and union_merge now says why

**Kind:** filing
**Filed by:** factory
**Status:** proposed
**Date:** 2026-11-26 07:00 EST. Written by the factory coordinator (FCT-5, a Desktop session). Reports what the factory experienced. How seldon answers is Seldon's.

## What the factory experienced

1. **A return task was held by a wait that could not clear.** `seldon cc return` wrote squiddy's SQ-143 (`627c92ed`,
   the return for SEL-043) on 2026-11-24 with the header
   `**After:** 2026-11-12_consumer_filing_from_seldon_the_operators_statement_of_a_coarse_tier_...`. That file is
   consumer filing `750348cb`: `task_kind` filing, never a dispatcher candidate, so it never completes. Registration
   turned the header into a `PRECEDES` edge (reason "declared in the task file's **After:** header"). SQ-143 sat
   `proposed` from 2026-11-24T23:33Z with nothing saying the wait was permanent. No person wrote that header. The
   coordinator removed the edge by hand on 2026-11-26 (`seldon_task_unprecede`, squiddy commit `048c6a0e`). The
   header is still in the task file, which is immutable.

2. **`seldon dispatch status --json` writes a warning line into the stream that carries its JSON.** Seen by SEL-047
   (`docs/evidence/sel047/README.md` Part E item 2, under `test_sel018_relative_dispatch_paths`). A reader that
   parses the output gets a non-JSON first line.

3. **The MCP portfolio brief returned one project.** `seldon_go(project_dir=/Users/brock/GitHub/factory, brief=true,
   portfolio=true)` at 2026-11-26 about 11:40Z (code `d573df2`) returned the same text as the call without
   `portfolio`: factory's own state and dispatcher only, about 30K tokens, no section for seldon, squiddy,
   hazbrief-mcp or critical-thinking-ai. The tool list inside that answer names `seldon_go(project_dir, brief,
   portfolio)`; the schema the Desktop client was served names only `project_dir` and `brief`. The coordinator's
   procedure (factory `CLAUDE.md`, "Start with `seldon go --portfolio --brief`") therefore could not be followed from
   Desktop, and state was read from each graph by hand again (factory F-031 names that as the thing to stop).

4. **`test_union_merge_of_two_event_appends_is_valid` now says why it fails.** SEL-049's full `-n 6` run: 1 failed,
   `merge_blocked`, `main_kept_moving` after 3 attempts. It passed in SEL-050's run. About 1 run in 10 since SEL-047.
   A full gate that goes red on it costs a 26 to 40 minute rerun.

## What the factory wants to know back

- For 1: whether a return task can still be written with an `After:` naming a non-candidate, and whether any other
  open return task in a registered repository carries one now.
- For 3: whether the portfolio brief is reachable from the MCP tool today, and at what size.
- For 2 and 4: whether seldon takes them, and when, given factory F-027 item 3 (tool work answers a project's
  friction; 3 and 4 are the factory's and the gate's own).

## References

squiddy `cc_tasks/2026-11-24_SQ-143_a_consumer_s_dispatcher_waits_on_a_producer_only_for_what_can_hurt_it.md`;
seldon `docs/evidence/sel047/README.md` Part E; SEL-049 and SEL-050 RESULTs; factory `decisions.md` F-029 item 2,
F-031; factory handoff `2026-11-25_FCT-4_...md` items 2 and 5.
