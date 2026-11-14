# Filing from factory: the operator has no portfolio entry point

**Kind:** filing
**Filed by:** factory
**Status:** proposed
**Date:** 2026-11-13. Written by the factory Desktop session (FCT-2). Replaces the entry-point section of filing 5dcad91f, withdrawn the same day because its other sections were wrong. Reports what the factory experienced; the answer is Seldon's.

## What the factory experienced

The operator runs `seldon go` and reads a handoff in one repository at a time. On 2026-11-13 he said he now starts at
the factory and expects a factory-level go and handoff. Factory F-016 records that the factory is Seldon at portfolio
scope and that the factory will not build a second engine.

Today a `go` or a handoff in the factory repository reads the factory's graph only. The factory coordinator gathers
every other repository's state by hand, one `seldon_task_list` call per repository plus a read of each
`.seldon/dispatch_last_pass.json`, as it did on 2026-11-01, 2026-11-02 and 2026-11-13. On 2026-11-13 that hand
gathering missed that seldon had built requirements as graph content four days earlier (AD-013-R1, SEL-033, SEL-035),
and the factory designed around a gap that did not exist.

## What the factory needs, stated as an outcome

One brief in the factory repository lists every registered repository's open tasks, running task, last dispatcher
pass, alarms and what each has completed since the last brief, with counts equal to each repository's own task list;
one handoff carries per-repository sections and one resume line.

## References

factory `decisions.md` F-011, F-016; factory `docs/plan.md` stage 3d; factory `registry.md`.
