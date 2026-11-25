# Filing from factory: seldon's merge gate holds every queue, and the portfolio order is gate first

**Kind:** filing
**Filed by:** factory
**Status:** proposed
**Date:** 2026-11-24 22:45 EST. Written by the factory Desktop session (FCT-3). Reports what the factory experienced and the order the factory has recorded for the portfolio. How seldon does its work is Seldon's.

## What the factory experienced

On 2026-11-24 factory's dispatcher was refused `environment_in_flight` (a dispatcher holds a lease on seldon) from
19:16 EST while SEL-043 round one ran its session and its 86-minute merge gate. FAC-08R launched only after that
round ended, about 80 minutes later. From 20:50 EST, when SEL-043 round two launched, factory's FAC-06R, FAC-09 and
FAC-10 have waited the same way, and will wait through round two's gate. Each of those factory tasks is a few
minutes of work behind a 14-second gate. SEL-043 is the change that ends this wait, and it is the task holding the
lease.

The operator pasted the seldon thread's 20:55 report into the factory thread and said: "I want to be able to
coordinate everything. Guess I'm not just sure how to get out of this spiral."

## The order the factory has recorded (factory `decisions.md` F-027, 2026-11-24)

1. After what is in flight (SEL-043 round two, SEL-044), the only seldon work is the merge gate's time (Issue
   `d6040ce8`'s two load flakes, then the parallel suite) until a merge that touches `tests/conftest.py` gates in
   under 30 minutes.
2. A task that comes back red from the merge gate twice is parked on its kept branch and not driven a third time
   until item 1 is done. If SEL-043 is parked, SEL-044 is not held behind it.
3. No new tool task is written unless it answers a friction-log row from a project in use.
4. One coordinator: the seldon thread retires when SEL-043 round two resolves, by writing its handoff, and seldon's
   queue is then read and driven from the factory thread.

The operator has not objected to F-027 and can override any item.

## What the factory needs, stated as an outcome

Seldon's queue follows that order, and whichever thread next reads SEL-043 round two's outcome knows it before it
redrives anything.

## References

factory `decisions.md` F-020 as amended, F-026, F-027; factory `friction-log.md` rows of 2026-11-24; seldon Issue
`d6040ce8`; SEL-043 ADDENDUM 01.
