# Filing from hazbrief-mcp: from a worktree the decision register reads its imported registers as empty, and an importer's projection goes stale when an import adds records

**Kind:** filing
**Filed by:** hazbrief-mcp (HB-240, a dispatched CC session in a worktree, 2026-11-27)

## Observation

1. `seldon.core.decisions.settings` resolves `decisions.repositories` (hazbrief: `seldon: ../seldon`, `squiddy: ../squiddy`)
   and the side-by-side default for `decisions.import` against `Path(project_dir).resolve()`. In a worktree
   (`<repo>/.claude/worktrees/<name>`) that is `<repo>/.claude/worktrees/seldon`, which does not exist, and the register
   there reads as zero records with no error. `seldon.core.worktree.anchor` exists for exactly this (SEL-018), and
   `cross_project` uses it; the register does not. hazbrief's own `seldon.yaml` comment says the paths are "Resolved
   against the primary checkout from a worktree", which is not what the code does.
2. The merge round projects the register only when the merged branch brought pending records of the importer's own
   register (`dispatch_worktree.number_merged_register` returns before `_project_register` otherwise). Records an
   imported repository adds are never projected into the importer's graph by anything automatic.

## Evidence

- In the HB-240 worktree, 2026-11-27: `seldon decision list --repo seldon` printed `0 record(s)`; the primary checkout's
  `seldon verify` reported `projection: 59 record(s) not projected as the register says (first: seldon:AD-034-R29,
  seldon:AD-034-R30, ...)`, and the worktree's `seldon verify` reported no projection finding at all, because it read
  none of seldon's 253 or squiddy's 541 records. A worktree's `seldon decision project` therefore cannot repair the
  primary's finding, and a worktree's verify, decision check and registration binding silently omit every import.
- Factory's spec check (2026-11-26) rated hazbrief `seldon_verify` CRITICAL on this projection finding (item 1 of 2).
- HB-240 repaired it by calling `seldon.core.decisions.project` with the sibling paths anchored at the primary checkout:
  `hazbrief-mcp/docs/evidence/hb240/repair_register.py` (58 created, 1 updated, 1 `amends` edge).

## Also, the stale binding route (hazbrief Issue 2fa4990b, open since 2026-11-21)

`seldon verify` fails on any `constrained_by` edge to a Decision that is no longer accepted, whatever the task's state,
and a supersession never moves or ends those edges; `seldon link` has only `create`. HB-240 ended HB-214's edge to the
superseded `hazbrief-mcp:HBD-474` with `seldon.core.artifacts.remove_link` (a `link_removed` event), the same thing
`seldon verify --fix` does for a Ruling (`governed.prune_non_binding_constraints`). A command for it, or `--fix`
covering Decision edges, would let the next session do this without a script.

## Effect on the consumer

Each new seldon or squiddy record leaves hazbrief's `seldon verify` CRITICAL on the primary checkout until someone runs
`seldon decision project` there, and no dispatched hazbrief session can run it to effect. The same holds for every
repository that imports a register and works in worktrees.
