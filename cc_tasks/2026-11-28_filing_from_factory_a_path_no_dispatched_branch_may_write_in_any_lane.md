# Filing from factory: a path no dispatched branch may write, in any lane, so an operator's answer cannot be merged in

**Kind:** filing
**Filed by:** factory
**Date:** 2026-11-28
**Reporter:** factory FAC-71 (REVIEW-002 finding F-04), a dispatched Claude Code session.

## What was experienced

factory's bank applies an answered top-up as the operator's grant. He answers a `for_operator/` item by editing it and
moving it to `for_operator/done/`. REVIEW-001 F-03 took `for_operator/done/` out of factory's coordination lane
(`dispatch.coordination_lane.writes` is now `['cc_tasks/**', 'for_operator/[0-9]*.md', 'bank/grants/**']`). REVIEW-002
F-04 found the other ways in: a build-lane branch may write any path, so a task branch that writes
`for_operator/done/<item>.md` with `approved_tokens` filled in merges on green, and `done/` then holds an "answer" no
operator gave.

## What the evidence shows

- `seldon/core/lane.py`: `writes` globs bind only the coordination lane. A build-lane task has no write set, so the
  merge gate takes any path it changed.
- factory has no way to say "no dispatched branch, in any lane, may change this path". The lane narrowing itself rests
  on a naming convention (an item's name starts with its date, `done/` with a letter) and on `fnmatch` semantics
  (`*` crosses `/`).

## What factory does meanwhile

FAC-71 closed the tick's half: the tick applies an answered top-up only when it committed that `done/` copy itself, as
a move it saw in the primary's working tree (`scripts/coordinator_tick.py` `operator_moves_step` records it in state
`operator_moved`; `bank_step` refuses any other). A `done/` copy that arrives by a merge is put to judgment. What stays
open is recorded in factory's DN-004 ADDENDUM 03, "What it does not close": `bank.audit` on read still trusts
`for_operator/done/`, so a grant line written through `bank.py` from a merged `done/` copy reads as his.

## What factory asks

Could seldon's dispatcher hold a project-declared list of protected paths (for example `dispatch.protected_paths:
['for_operator/done/**']`) that no dispatched branch may change in any lane? A branch that does would be refused at the
merge gate with a named reason, as a lane write outside `writes` is today. Path matching would use the same function
for every lane, with a `*` that does not cross `/`, or with the semantics stated where the list is declared.
