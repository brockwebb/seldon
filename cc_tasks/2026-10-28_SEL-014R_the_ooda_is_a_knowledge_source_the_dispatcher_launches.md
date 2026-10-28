# SEL-014R: the OODA between chained tasks is a knowledge source the dispatcher launches, and a mechanical refusal is retried under a rule

**Status:** proposed
**Author:** Desktop session (seldon), 2026-10-28. Re-filing of SEL-014 (registration refused `premise_false`: `ooda_grace_s` is a code default, not a seldon.yaml key), from the squiddy SQ11 work order (`handoffs/2026-10-28_desktop_sq11_the_factory_runs_without_the_desktop_work_order.md`, items W1, W2, W4).
**Repo:** seldon (primary). L4: commit, merge, push in seldon.
**After:** a3357104
**Governing:** AD-038-R10 and R11 (c18, the Desktop OODA, `docs/conventions/desktop_ooda.md`); AD-038-R5 and R12 (registration runs premises and the static checks); AD-038-R13 (`seldon task number`); AD-037-R6 (stations). Write the design note first (Part A) and number its rulings under AD-038; the note's prior-art receipts are re-run in seldon, since the SQ11 searches were logged in squiddy.
**Model:** primary
**Spend:** est. 1.2M tokens. Basis: one design note with its prior-art pass, one new session kind launched by the dispatcher (reuses the worktree launch and the stop-gate stations), three record types, the registration retry, fixtures that replay last night's four-task chain. The OODA session itself makes model calls; cap at 0.3M per OODA run in `seldon.yaml`.
**Network:** none beyond git push.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes (edits seldon/core/dispatch.py and seldon/commands/cc.py)
**Parts:** A 0.25, B 0.40, C 0.20, D 0.15.
**Premises:**
- premise: c18 and the Desktop OODA convention exist | check: test -f docs/conventions/desktop_ooda.md
- premise: the grace timer is the only fallback today, by code default | check: grep -q "OODA_GRACE_S_DEFAULT" seldon/core/dispatch.py
- premise: last night's chain ran on grace with no OODA record | check: sh -c "test $(grep -c ooda_recorded seldon_events.jsonl) -le 2"

Checks are single commands with no shell.

## The condition

SEL-010R2 built c18: a chained task waits for a Desktop OODA record on its predecessor. On 2026-10-27/28 four seldon tasks (NUM-001R → DESK-004R → DISP-004R → RECALL-002R) and four squiddy tasks (SQ-052R → SQ-086R → SQ-089R → SQ-096) ran unattended and completed; no OODA was performed, every chain proceeded on grace, and nothing was worse for it. The step as designed needs a human surface; the factory runs without one. Separately, three registrations in one morning were refused for mechanical causes a human fixed by hand (`number_taken`; a `check:` with `&&` or `$(...)` not under `sh -c`; a premise naming an evidence file that does not exist).

## Prior art, to be received in seldon's log in Part A

Blackboard architecture: Hearsay-II (Erman, Hayes-Roth, Lesser, Reddy 1980, ACM Computing Surveys 12(2)); Hayes-Roth, "A blackboard architecture for control" (Artificial Intelligence 26, 1985). Knowledge sources fire on the board's state and write back; a control component picks the next; none holds a conversation. Linda tuple spaces (Gelernter 1985) as the coordination form. Spreading activation (Collins and Loftus 1975) for "nearest nodes for context", of which Recall at registration is the thin instance. DeerFlow 2.0 (ByteDance, 2026) as a point of comparison, not a template: one goal per run, no governance between runs. Seldon's graph plus task files is already the board; the missing knowledge source fires on `task_completed`.

## What to build

**A. The design note.** `docs/design/AD-038_ADDENDUM_07_the_ooda_as_a_knowledge_source.md`: re-run the prior-art searches above through `seldon prior-art search` so the receipts are seldon's; rule W4 as **advisory**: a chain proceeds unless the record is `ooda_blocked`; `ooda_grace_s` is retired as the gate and kept only as the timeout on the OODA session itself. Number the rulings. `seldon prior-art verify` must pass before Parts B to D dispatch.

**B. The knowledge source.** On `task_completed` for a task with an open successor, the dispatcher launches a headless OODA session in a worktree: `seldon go --brief`; read the RESULT and the successor file; run the successor's premise checks against HEAD; pull Recall for the predecessor and its governing note. It ends in exactly one record: `ooda_ok` (chain proceeds); `ooda_amended` (an ADDENDUM for the successor is written and committed through the hooks: a moved path, a premise the predecessor made true or false, a number, a check that needs `sh -c`; chain proceeds); `ooda_blocked` (a question no ruling answers; the record names the question and the note that would answer it; the chain halts; `seldon_ooda_pending` lists only these). A session that fails or times out writes `ooda_expired` and the chain proceeds, so a checked chain is distinguishable from one that ran on the timer. Cost cap per run in `seldon.yaml`.

**C. The retry at registration.** The same knowledge source fires on a registration refused for a mechanical cause: `number_taken` → next number from the allocator; a check failing "unexpected operator" or "bad number" → wrapped in `sh -c`; a premise naming a path absent from a named repository → marked `stale_evidence` and narrowed to what exists. One retry, logged on the task as `registration_retried` with the rule applied; a second refusal reaches a human as today. Build it as one module with B.

**D. Acceptance.** Replay last night's seldon chain (the four RESULTs are on main) through B in a fixture: four records, each `ooda_ok` or `ooda_amended`, zero human reads; and a fixture successor whose premise the predecessor broke produces `ooda_amended` with the addendum committed. Record every OODA run's tokens in the RESULT.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 1.5M.

## Deliverables

A to D; `cc_tasks/2026-10-28_SEL-014R_the_ooda_is_a_knowledge_source_the_dispatcher_launches_RESULT.md`.
