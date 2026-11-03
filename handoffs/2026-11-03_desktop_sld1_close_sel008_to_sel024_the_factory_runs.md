# Handoff: seldon Desktop thread SLD-1 closes (2026-10-24 to 2026-11-03)

**From:** the seldon Desktop thread SLD-1. **To:** the next seldon Desktop thread. Read at `seldon go`; everything below is in the graph or the tree, this is the map.

## What this thread did

Registered SEL-010 through SEL-018 and SEL-023, SEL-024; wrote HB-70 ADDENDUM-02 and HB-73 in hazbrief; recorded one OODA (FRICTION-002). Everything registered here through SEL-018 ran and merged by the standing dispatcher with no hand launch; SEL-019 to SEL-022 were registered by other threads and also ran.

Landed, in order: SEL-010R2 (c18, `dispatch adopt`), SEL-011 (registration applies the dispatcher's static checks; every non-candidate gets a reason line), NUM-001R, DESK-004R, DISP-004R, RECALL-002R (one four-task chain, unattended overnight), SEL-012 and SEL-015 (pass-ledger hook, all repos), SEL-013R (`Answers:` and `cc return`, AD-036-R16), SEL-014R (the OODA as a knowledge source, AD-038 ADDENDUM 07; W4 ruled advisory), SEL-016 (hazbrief has a dispatcher), SEL-017 (session links clean, worktree hook, Parts defaults; AD-034-R14), SEL-018 (relative `dispatch:` paths resolve at the primary checkout).

## Queue as of 2026-11-03 09:10 EST

- **SEL-023** (841bd7c7), After: none. Answers the squiddy consumer filing of 2026-11-03 (`cc_tasks/2026-11-03_consumer_filing_from_squiddy_...md` plus ADDENDUM-01) and the SQ11 addendum's W7, W8: `Kind: filing` registers without candidacy headers; `Dispatch: hand` is refused by the dispatcher; one call writes, commits and registers; every pass pushes when ahead; the consumer-thread rule goes in the system CLAUDE.md; Part E files the return to squiddy.
- **SEL-024** (0d115437), After: SEL-023. SQ11 addendum W6: the merge gate requires the project's declared pass record (`dispatch.gate_record:`) for the tip it merges; "environmental" is `gate_unrunnable`, never a pass.
- Pre-October residue, all `no_source_file`, deferred on purpose: SEL-003 (needs the operator's spend decision, ~11M est., then an R file), SPEC-001 (767f0d03), the secrets-layering standard (15792854), three ai-readiness-kg CLI defects (814e95d7, 066e5b69, 83134297), 1581c3ec blocked.

## Open, not tasks

1. AD-038's base note cannot pass `prior-art verify` until its library receipts are re-run (Issue dbe38fac); SEL-014R's rulings are advisory until then. Recipe in SEL-014R's RESULT, "Open" 1.
2. Two seldon huddles (ac19fab1, 2cc7a4de) and two stale DO NOW issues (SEC-001 0fd2742a, STD-001R 8788b2ef) from mid-October. Hygiene; the issues are MCP calls on the operator's word, the huddles are CLI.
3. HB-71 was running in hazbrief at 2026-10-30; hazbrief's two kept worktrees and leases (rosy-sprouting-stroustrup, floating-snuggling-waffle) were to be reaped by an HB task. Check hazbrief's board before assuming.

## Rules this thread learned the expensive way

- A committed task file is immutable and the registrar and dispatcher read headers from the base file only. Fix a bad header with an R file (SEL-010R, SEL-010R2, SEL-013R, SEL-014R were all this). Check every premise by command before committing: the device shell mounts repos at `$HOME/mnt/<repo>`, so a Mac path in a check must be tested against the mount, not taken on faith.
- `Exclusive: no` needs `Touches:`; when in doubt, `Exclusive: yes`.
- A Desktop session cannot launch a Claude Code session; only a dispatcher can. "Dispatch" from a Desktop means register and let the pass take it. The operator pastes nothing into a CC window.
- The dispatcher reaps only what it completed; a task completed through the lifecycle path leaves its worktree and lease behind.
- The dispatcher rotated its log to `logs/seldon_dispatch.log.<stamp>` once (2026-10-28), a name the ignore misses; it was moved under `logs/dispatch/` with a `.log` suffix. If it recurs, the rename belongs in a one-line task.

## Message traffic

Three Desktop threads talk to seldon through the operator: hazbrief (HB-prefixed), squiddy (SQ11, SQ12), ai-readiness-kg (AR-7). Each reply is a paste block the operator carries. Answer in their order, name ids and commits, and never give them a launch line.
