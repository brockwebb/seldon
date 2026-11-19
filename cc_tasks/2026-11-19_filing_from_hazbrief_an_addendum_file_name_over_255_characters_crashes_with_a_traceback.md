# Filing from hazbrief-mcp: filing an addendum whose file name exceeds 255 characters crashes with a Python traceback instead of a plain refusal

**Kind:** filing
**Filed by:** hazbrief-mcp
**Date:** 2026-11-19
**Reporter:** hazbrief Desktop thread, relayed by the operator to the seldon Desktop session SLD-2 at 12:33 EST and written here by that session in hazbrief's words. The operator's instruction: "queue up for fix Saturday" (2026-11-21, after hazbrief's 2026-11-20 submission).

## What hazbrief experienced

Filing an addendum whose file name exceeds the 255-character limit crashes with a Python traceback (`OSError: File name too long` in `filing.py` line 292) instead of a plain refusal. HB-207's long task name leaves about 50 characters for an addendum's slug.

## What the evidence shows

- The traceback names `filing.py` line 292 and `OSError: File name too long`.
- An addendum's file name is its task's full stem plus `_ADDENDUM_NN_` plus a slug, so a task whose own name is near the limit leaves little or nothing for the slug. HB-207's stem leaves about 50 characters.
- The seldon session has not reproduced this; it is recorded as reported.

## What is asked

That the case be handled. Not to run before 2026-11-21.
