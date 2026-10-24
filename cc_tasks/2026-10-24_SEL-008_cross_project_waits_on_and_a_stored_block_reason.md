# SEL-008: a task can wait on a task in another project's graph, and a block stores its reason

**Status:** proposed
**Author:** Desktop session (hazbrief), 2026-10-24
**Repo:** seldon (primary). L4: commit, merge, push in seldon.
**Governing:** AD-030 (task registration and the event ledger); AD-034 and AD-038 (the dispatcher's criteria vector and redrive). If the state machine's definition lives under another AD, cite it in the RESULT and say so.
**Model:** primary
**Spend:** est. 0.4M tokens. Basis: one new relationship kind with validation, one new task property, a dispatcher check against a second graph, tests. Zero model calls.
**Network:** none beyond git push.
**Exclusive:** no
**Parts:** A 0.35, B 0.25, C 0.40.
**Premises:**
- premise: the SQ-048 dependency is named in hazbrief's handoff | check: grep -q SQ-048 /Users/brock/GitHub/hazbrief-mcp/handoffs/2026-10-24_desktop_build_to_graph_rating.md
- premise: HB-20 (311388f9) is in hazbrief's ledger and was set blocked on 2026-10-24 | check: grep -q 311388f9 /Users/brock/GitHub/hazbrief-mcp/seldon_events.jsonl

Checks are single commands with no shell. The absence of a stored block reason is Part B's first test to confirm by reading the domain config; the single `precedes` edge on HB-20 is confirmed by `seldon task show 311388f9` in hazbrief.

Glob and read every sibling `*SEL-008*ADDENDUM*.md`.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.5M.

## The defect

hazbrief task HB-20 (`311388f9`, "open the concept and topic layer over the claims") ran on 2026-10-23 and stopped on a Squiddy defect, filed as squiddy SQ-048. On 2026-10-24 the hazbrief graph showed HB-20 as `proposed` with one edge, HB-19 precedes it, and the dependency on SQ-048 in a handoff paragraph. A dispatcher reading that graph would have launched HB-20 and watched it fail at the same call. Three gaps:

1. **No cross-project edge.** A `precedes` edge can only name a task in the same graph. SQ-048 is a node in `seldon-squiddy`. Projects that feed each other (hazbrief files defects to squiddy and waits on them; squiddy files to seldon) have no way to say so in the graph, and the operator's "the graph is the source of truth" does not hold for this class of dependency.
2. **`blocked` is reachable only from `in_progress`.** Marking HB-20 blocked from Desktop took three transitions (proposed → accepted → in_progress → blocked), the middle one recording a `claimed_by: desktop` that was not true. A known dependency should be recordable at registration or from any open state.
3. **A block has no stored reason.** `seldon_task_update`'s note is echoed back and not stored. `blocked` with nothing attached cannot be redriven by a rule; only a person who remembers why can lift it.

## Part A: `waits_on` across graphs

1. Test first: `seldon task precede` (or a new `seldon task wait-on`) accepts a target of the form `<project>:<task-prefix>` where `<project>` is a Seldon project name resolvable to its graph (as the decision register's imports resolve a repository). It writes an event in the waiting project's ledger only; the other graph is read, never written. A target that resolves to no task is refused before any write (SEL-007's rule).
2. `seldon go` and `seldon task show` print the edge with the other project's task state as of the call.

## Part B: `blocked` from any open state, with a reason

3. Test first: `seldon task update <id> blocked --reason <text>` is valid from `proposed`, `accepted` and `in_progress`; the reason is stored on the node and in the event; `blocked` with no reason is refused. `seldon_task_update` (MCP) takes the same `reason`.
4. `seldon task list` prints the reason beside `[blocked]`.

## Part C: the dispatcher reads both

5. Test first: the criteria vector treats a task with an unsatisfied cross-project `waits_on` as not ready, and a task whose `waits_on` target has reached a terminal success state as ready again (the automatic redrive AD-038-R2 describes, applied here). The other graph unreachable is "not ready", logged, never "ready".
6. `seldon verify` gains a check: a `blocked` task with no reason, or a `waits_on` whose target no longer resolves, is a finding.
7. Gate; commit; push. In the RESULT, name any project whose ledger needs a backfill (hazbrief HB-20 at least) and the command to do it; do not run it in another project.

## Deliverables

Code, tests, the verify check, `cc_tasks/2026-10-24_SEL-008_cross_project_waits_on_and_a_stored_block_reason_RESULT.md`.
