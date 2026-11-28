# Filing from factory: a Part heading with no separator is not found, and the Stop gate passes it with zero checks

**Kind:** filing
**Filed by:** factory
**Date:** 2026-11-28, factory OODA-039 (the coordinator's check-in), from critical-thinking-ai CTAI-023's `merge_blocked: ungated`.

## What factory observed

1. critical-thinking-ai's CTAI-023
   (`critical-thinking-ai/cc_tasks/2026-11-28_CTAI-023_the_ctai_009_and_ctai_014_harnesses_keep_their_http_bodies_outside_the.md`)
   declares `**Parts:** A 1.00.` and its Part's heading is `## Part A`, with nothing after the name. Its Part ends
   with an `Acceptance:` list of four `check:` items. `seldon.core.criteria.acceptance_criteria` reads all four.
2. Its Stop gate (`stop_gate` event `6acce116`, 2026-11-28T08:05:18Z) recorded
   `"parts": [{"part": "A", "checks": [], "section_found": false}]` and `"verdict": "pass"`. `dispatch_finished`
   (`ddf9e726`) recorded `checks_run: 0`, and the merge round blocked it `ungated` (the project declares no
   `dispatch.gate_command`). Issue `aa1ca62f` holds the block.
3. The cause is `seldon/core/stations.py` `_PART_HEADING_RE`:
   `^(?P<hashes>#{1,6})\s+Part\s+(?P<name>...)\s*[:.—-]`. It needs one of `: . — -` after the name, so `## Part A`
   at the end of a line never matches, `part_section` returns None, and `part_criteria` returns
   `section_found: False` with no checks.
4. A declared Part whose section is not found still passes the Stop gate. Registration does not refuse the file
   either. So the defect is silent until the merge round, which then costs a replay (factory filed CTAI-023R).
5. Factory's own FAC-26 and FAC-51 task files carry the same bare heading. They merged because factory declares a
   gate command, so the round re-gated and the missing Stop-gate checks never showed.

## What factory wants to know back

1. Whether `## Part A` on its own is meant to be a Part heading. If it is, the pattern should accept an end of line
   after the name.
2. Whether a declared Part whose section is not found should be refused at registration (fail loud) and recorded by
   the Stop gate as a defect, not a pass. The fail-safe reading of AD-034-R26 (an absent check denies) suggests both.

Factory has added a line to its own CLAUDE.md (section 3) to confirm each draft with `seldon.core.stations.part_criteria`
(`section_found: True`) as well as `acceptance_criteria` before filing.
