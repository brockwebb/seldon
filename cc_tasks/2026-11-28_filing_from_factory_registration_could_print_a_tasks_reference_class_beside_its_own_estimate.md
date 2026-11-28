# Filing from factory: registration could print a task's reference class beside its own estimate

**Kind:** filing
**Filed by:** factory
**Date:** 2026-11-28
**Reporter:** factory FAC-61 Part C (DN-006 decision 6), a dispatched Claude Code session.

## What was experienced

FAC-61 measured every dispatched task with a Spend and a meter reading across the registered repositories (436
tasks; the dispatcher's readings, as factory's bank reads them). Actual over estimate has a median of about 0.35: most
estimates are about three times what the work spends. For the tasks first launched on 2026-11-26 and 27, their own
estimates were off by a median factor of 3.5, and the median actual of earlier tasks of the same class (classed by
rule from the name, headers and text) was off by 1.4. The class median alone would have put about a third of those
tasks past the 1.2 spend ceiling, so it is a figure to show, not one to adopt blindly. Full table and method:
`factory/site/lessons.html` (Estimates), `factory/state/lessons.json` (`estimates`), and
`factory/cc_tasks/2026-11-27_FAC-61_..._RESULT.md`.

## What factory asks

Could `seldon cc file` (and registration generally) print, beside a task's own `**Spend:**`, its reference class's
figures, read from the factory's own command so seldon owns no copy of the rules:
`/opt/anaconda3/bin/python /Users/brock/GitHub/factory/scripts/estimate.py <task file> --from-state` prints the class,
its count, its median and 80th-percentile actual, the spread of actual over estimate, and the draft's own estimate
over the class's median (exit 0; 2 when it cannot read, which registration would show and not act on)? Printing only:
the estimate stays the author's, and nothing is refused on it.

## What factory does meanwhile

The tick's own templates (OODA, replay, answerer) take their Spend from their class (`coordinator_tick.py`
`template_spend`); any author can run `scripts/estimate.py` on a draft by hand.
