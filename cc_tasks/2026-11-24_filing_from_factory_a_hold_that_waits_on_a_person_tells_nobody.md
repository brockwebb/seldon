# Filing from factory: a hold that waits on a person tells nobody

**Kind:** filing
**Filed by:** factory
**Status:** proposed
**Date:** 2026-11-24. Written by the factory Desktop session (FCT-2). Reports what the factory experienced and what the operator reported; the answer is Seldon's.

## What the factory experienced

Factory task FAC-06 (b62cd550) finished its work on 2026-11-14 and was marked `blocked: dispatcher: merge_blocked`.
It stayed that way until 2026-11-24, ten days, when the coordinator redrove it by hand. In that time nothing notified
anyone: the stuck alarm did not fire, because the dispatcher was passing cleanly with nothing to launch, and the block
was visible only to a thread that asked for the task list. The coordinator read that list on 2026-11-19 and 2026-11-21
and left the block alone as "waiting on SEL-042" without checking when SEL-042 had landed.

## What the operator reported from hazbrief's submission week

From the hazbrief thread's account of the night of 2026-11-23, pasted to the factory by the operator: about 150
minutes went to stalls against about 91 minutes of gate runs. The stalls it names: a Desktop note committed without
its decision record, which turned main red and blocked a merge; a task that sat unlaunched for 90 minutes on a header
error; a merge block that waited for a redrive. Each waited on a person and told nobody. The factory has not read
hazbrief's event log to confirm these figures.

## What the factory needs, stated as an outcome

When a task or a queue is waiting on something only a person can do, a person hears about it once, with the reason
and what would clear it, without having to ask. The factory's plan page (factory F-023) will show every blocked and
held task with its reason and age; a page nobody is looking at does not ring.

## References

factory `friction-log.md` rows of 2026-11-24; factory `docs/gaps.md` G-39; factory `decisions.md` F-019 (an outlet
that is slow or silent is a wall), F-026.
