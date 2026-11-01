# SEL-022: the DD-007 refusal rings the stuck alarm once and stops dirtying the event log

**Status:** proposed
**Author:** the factory Desktop session (FCT-2), 2026-11-01.
**Repo:** seldon. L4: commit, merge, push. No other repo is written.
**After:** 2026-11-01_SEL-020_project_new_ignores_its_state_governed_commit_paths_per_project_and_factory_adopts
**Governing:** factory `docs/plan.md` stage 2 and `docs/gaps.md` G-06; factory friction log 2026-11-01 (hazbrief refused 17 hours with no alert); DD-007; AD-038-R6 (FRICTION-001 Part E, `database_unavailable` written once per outage); the `dispatch_stuck` design in `seldon/core/dispatch.py` (ADDENDUM_01 to ai-readiness-kg 2026-09-19 hygiene task, decision 6b) and DESK-001 Part B; AD-032 FC-28 (andon).
**Model:** primary
**Spend:** est. 0.4M tokens. Basis: FRICTION-001 Part E's outage-once pattern is the template; one refusal path moved onto it with tests. Zero model calls.
**Network:** none beyond git push.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** no
**Touches:** seldon/commands/dispatch.py, seldon/core/dispatch.py, tests/, docs/design/
**Parts:** A 0.85, B 0.15.
**Premises:**
- premise: `api_key_present` is emitted at its own site before the lease | check: grep -q "api_key_present" seldon/commands/dispatch.py
- premise: the stuck streak and `notify` exist | check: grep -q "EVENT_STUCK" seldon/core/dispatch.py

Glob and read every sibling `*SEL-022*ADDENDUM*.md`.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.6M. Stop and report if the fix needs the lease taken before the DD-007 check (the check must stay before
any claim and before the lease), or if any other refusal's behaviour would change.

## Why

From 2026-10-31 07:42 to 2026-11-01 00:57 hazbrief-mcp's dispatcher refused every pass because the one-day API key
had been added to its `.env`. The guard was right. Nothing surfaced it: `api_key_present` is refused before the
lease and outside the stuck streak, so it never reaches `dispatch_stuck` or `dispatch.notify`; and because it is
handled as an occurrence, it appends to the tracked `seldon_events.jsonl` on every pass, which kept the tree dirty
and would have refused the queue on c7 even after the key was removed. Every other standing condition already
rings once (`dirty_tree` on the first pass, `database_unavailable` once per outage).

## Part A: standing pre-lease refusals join the streak

1. `api_key_present` becomes a standing condition: written once per outage (state file beside the lease, as
   `dispatch_outage.json` is), counted in the stuck streak with the criterion name and the variable name (never
   its value), and `notify` runs once when the streak reaches its threshold. The first pass without the key clears
   the outage state and the streak.
2. Default `stuck_after_passes_by_criterion` gains `api_key_present: 1`: it never clears by itself.
3. `lease_held` is unchanged while the holder PID is alive (a healthy long run). When the holder PID is dead, the
   refusal joins the streak the same way, naming `lease reap` as the remedy; nothing reaps automatically.

Tests (scratch repo, stub `claude`, zero model calls): a planted `ANTHROPIC_API_KEY` in `.env` produces exactly one
`dispatch_stuck` naming `api_key_present` and one `notify` run within the threshold; ten more refused passes add no
line to `seldon_events.jsonl` and leave `git status --porcelain` empty; removing the key lets the next pass proceed
and clears the state file; a dead-PID lease raises one stuck event naming `lease reap`; a live-PID lease raises
none; the existing byte-identical-log test for an empty pass still passes; the DD-007 child-environment strip is
untouched.

## Part B: the record

RESULT: the test names; the event lines a planted-key run writes, verbatim; a sentence added to SEL-005's design
note under "Events" saying which refusals are standing and ring once.
