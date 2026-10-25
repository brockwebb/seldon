# SEL-010: `seldon dispatch` waits for the Desktop OODA between chained tasks, and a project adopts it in one step

**Status:** proposed
**Author:** hazbrief Desktop session, 2026-10-25 (a finding while using the kit; filed under hazbrief's standing rule that kit defects found in a project go back to the kit)
**Spend:** none.
**Network:** none.
**After:** none

Cites `docs/design/2026-09-15_standing_dispatcher.md` ("reading a RESULT, naming its wrong premises and authoring the next task is still a Desktop OODA and is not automated here, DN-006 §4"); SEL-008 Part C (c17, cross-project waits); AD-038-R2 (redrive).

## The condition

The dispatcher closes the latency between a clean gate and a launch. It does not close the gap the operator hits when a chain of four tasks runs unattended for hours: nothing between task N's RESULT and task N+1's launch reads the RESULT, names the premises it found wrong, and amends N+1 before it starts. Today that step is a person relaying the RESULT into a Desktop thread. A chain dispatched while the operator is away therefore either runs every task on its original premises, or waits for the person. The operator's words, 2026-10-25: the OODA should be built into the agentic process, not done by hand at the end.

A second condition: a project with no `dispatch:` block (hazbrief) cannot opt in without hand-writing the block, a controls band reference and a launchd plist, and the candidacy headers (`Framework layer served`) are the first adopter's, not every project's.

## What to build

1. **An OODA gate between `precedes` edges.** A new criterion (c18): when task N+1's predecessor N completed, N+1 is eligible only once an OODA record for N exists, or a configured grace has passed. The record is a file beside the RESULT, `<N>_OODA.md`, or an event `ooda_recorded` naming N's id; its author is whatever Desktop process the project runs (a scheduled Desktop wake-up, or a person). The grace (`dispatch.ooda_grace_s`) is the project's choice, and `0` means never wait. Recorded as a value on `dispatch_launched` like the other criteria.
2. **`seldon dispatch adopt`**: writes the `dispatch:` block with every key filled from the project's existing config where it exists and asks for the rest, writes the launchd plist to a path it prints, and makes the candidacy headers a per-project list (`dispatch.candidacy_headers`) with `Spend` and `Network` as the kit-wide minimum.
3. **A Desktop wake-up recipe** in `docs/conventions/`: how a Desktop session schedules itself to read new RESULTs, write `<N>_OODA.md` and any ADDENDUM for N+1, and let c18 release the chain. This is the half of the loop the dispatcher note said it would not automate; the recipe says what the project runs instead.

## Deliverables

c18 with its fixture test; `seldon dispatch adopt`; the convention; `cc_tasks/2026-10-25_SEL-010_dispatch_waits_for_the_desktop_ooda_between_chained_tasks_RESULT.md`.
