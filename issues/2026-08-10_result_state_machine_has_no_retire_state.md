# Seldon Issue: the Result state machine has no retire/supersede state

**Date:** 2026-08-10
**Severity:** Substantive (forces a choice between a misleading record and an unclosable one)
**Found during:** `fss-policy-kg` v7.2 merge-back and v7.3 closeout (`~/GitHub/icsp_notebook`)
**Component:** Result artifact lifecycle — `seldon result register` / `verify` / `list`

---

## Problem

A Result has exactly two reachable states: `proposed → verified`. There is no way to record that a
Result **was true and no longer is**, or that it **cannot be verified as stated**. Both situations
are ordinary in a project whose corpus grows, and today both have to be forced into a state that
misrepresents them:

- **Era-bound values.** "62,233 nodes" was a correct v4 gate Result. At v7.3 the graph holds 62,469.
  The v4 number is not wrong — it is a measurement of a system that no longer exists — but the only
  states available are `proposed` (reads as "not yet checked", which is false) and `verified`
  (reads as "this is the number", which is now misleading). The current workaround is to verify the
  old value anyway and register a successor beside it, relying on the description text to tell a
  reader which is current. Nothing in the data model links them.
- **Condition-bound values.** `7c91e02d` in that project says in its own description
  "status=proposed pending the ensemble merge". The ensemble merge never ran. The Result cannot be
  verified without lying, and cannot be closed at all, so it sits in `proposed` indefinitely and is
  indistinguishable from a Result somebody simply forgot about.
- **Scaffolding.** A Result registered during setup with the description "TEST: …" has no honest
  end state either.

## The incident that made this concrete

During the v7.2 merge-back, a batch promotion filtered Results by `units` in order to verify the new
v7.2 measurements. The filter was too loose and swept in two v4-era Results — 62,233 nodes and 367
tests_passed — verifying them before they had been adjudicated. The end state happened to be
defensible (era-labelled historical Results already sit `verified` by convention in that graph, and
successors were registered beside them), but the process error was only recoverable *because* the
convention is "verify it anyway". A state machine that could express "this was true then" would have
made the mistake visible instead of absorbing it.

## What would fix it

A terminal state on Results — `superseded` (or `retired`) — reachable from `verified`, ideally
carrying a `superseded_by` link to the successor Result. That gives:

- `seldon result list` a way to show current values without hiding history;
- `seldon verify` something to say other than yes;
- a reader of an old paper section a way to find the number that replaced the one they are reading.

The link matters as much as the state. Today the relationship between "62,233 nodes (v4)" and
"62,469 nodes (v7.3)" exists only in prose inside two descriptions, which is exactly the
unregistered-number drift Results exist to prevent.

## Not urgent, and why it is filed anyway

Nothing is blocked: the workaround (verify, register a successor, explain in the description) has
been applied consistently in `fss-policy-kg` and is documented in that project's decision ledgers
(`cc_tasks/2026-08-10_c1_ordering_fix_DECISIONS.md` D26,
`cc_tasks/2026-08-10_post_v72_closeout_DECISIONS.md` D31). It is filed because the workaround is a
convention held in people's heads, and the next person to write a units filter will not know it.
