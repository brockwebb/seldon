# Filing from factory: declare the seldon_sessions grant premise in seldon's dispatch block

**Kind:** filing
**Filed by:** factory
**Date:** 2026-11-27
**Reporter:** factory FAC-48 (`factory/cc_tasks/2026-11-27_FAC-48_what_seldon_built_for_the_four_dispatcher_filings_of_2026_11_26_and_27.md`), item 2; seldon AD-038-R42 (SEL-054), which built what this uses; factory F-045
(the bank's weekly grants).
**Spend:** est. 0.1M tokens. Basis: one configuration block and one check run; no model calls of its own.
**Network:** none

## What is already in place, and what is seldon's

Since seldon SEL-054, a project may declare `dispatch.premises`: each a statement and a shell check, run before every
launch (serial, parallel and lane). A false one refuses the launch as `project_premise_false`, once per episode and
with no Issue; merges and redrives go on, and launches resume on the first pass where the check holds.

The factory's bank gives each project a `seldon_sessions` grant per allowance week (F-045). Today nothing stops
seldon's dispatcher from launching on a spent grant. The check below is what `/opt/anaconda3/bin/python /Users/brock/GitHub/factory/scripts/cost_manager.py premise --project seldon --unit seldon_sessions` prints; it exits 0 while the
grant has room and non-zero once it is spent (its output names the grant). It passed on 2026-11-27 when this was
filed. Factory declared the same premise for itself in FAC-48.

Nothing was written into seldon's tree. Declaring it is seldon's.

## Part A: declare it

1. First run `/opt/anaconda3/bin/python /Users/brock/GitHub/factory/scripts/cost_manager.py premise --project seldon --unit seldon_sessions`. If it prints a different `check:` command from the one below, use the printed one and
   say so in the RESULT.
2. In `seldon.yaml`, under `dispatch:`, add (with a comment citing this filing and seldon AD-038-R42):

       premises:
       - statement: "seldon's seldon_sessions grant has room"
         check: /opt/anaconda3/bin/python /Users/brock/GitHub/factory/scripts/cost_manager.py status --project seldon --unit seldon_sessions --stop-only

   If a `premises:` list is already there, append this item to it.
3. Run the check by hand and keep its output and exit code in the RESULT.

What NOT to do: do not copy factory's cost manager or bank into this repository; do not add a budget of its own.

Acceptance:
- `check: sh -c "grep -q 'cost_manager.py status --project seldon --unit seldon_sessions' seldon.yaml"` passes.
