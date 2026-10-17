---
title: "Where things stand, and the plan to get back on track"
subtitle: "17 October 2026, written at the weekly reset"
---

## Bottom line

- **The real progress this week was in ai-readiness-kg, and it is now waiting mainly on you.** It needs one page-two decision for the executive summary, plus Fable budget, which the reset restores.
- **The Arnold evidence graph, the squiddy kit's actual second product, has not moved since 4 October.** Its demand test missed narrowly: 0.475 against a 0.5 bar. Its factory has been paused since 4 October at a spend ceiling only you can set: 5.07M projected against 4.09M.
- **Squiddy and Seldon spent the week debugging their own machinery.** Squiddy's governed admission now runs in 25 to 30 seconds, a real gain. But six squiddy tasks in a row chased one stuck admission in arnold's engineering-docs graph, and each found a deeper defect instead of finishing. Seldon shipped seven tasks in eight days in a single chain of commit and registration fixes, each exposing the next gap.
- **The cause is structural, not bad luck.** Effort went into tools that were not the constraint on your outcomes. And one class of defect (machine-written state that another gate treats as foreign) was fixed one writer at a time.
- **The plan:** put the products first for the coming week, freeze new process machinery, close that defect class properly instead of patching its members, and set stop rules so a live test cannot absorb another week.

## 1. Where each piece stands

| Piece | State | Last real progress | Waiting on |
|------|----------------|---|------|
| ai-readiness-kg: working-group brief and executive summary | The instrument audit found 4 of the 13 public-tier checks defensible as specified. 86 of the 208 grid cells were unmeasured pages shown as fails, so the v3 summary built on that grid is withdrawn. A 4-page readiness brief with a 4-check agency grid exists (16 Oct), in Word and PowerPoint only. The v4 summary stopped when Fable's usage limit ran out. Dispatch is switched off in that repo. | 16 Oct | Your page-two choice; Fable budget (the reset restores it); dispatch switched back on |
| Arnold evidence graph | Built end to end 1 to 4 Oct: 749 documents catalogued, 448 in the graph. Its demand test (can the graph answer the questions it exists for) scored a lower bound of 0.475 against a pre-registered 0.5, so extraction stayed closed. The factory then paused at a spend touchpoint. | 4 Oct | Your ceiling decision; a design answer to the narrow miss |
| Library graph (the kit's proving ground) | Admitted 12 documents through the maintenance path; last release 12 Oct. | 12 Oct | Nothing urgent |
| Squiddy kit | Governed admission measured at p95 25 s (seldon) and 30 s (squiddy), down from a 13-minute run. arnold's engineering-docs graph still has one admission open (fix_caddy). The fix for its real cause (DN-048) is written and queued as SQ-017. | 16 Oct | DESK-002R registering SQ-017 |
| R-186 exit bar (governed admission across the three repos) | seldon and squiddy pass. arnold passed on 13 Oct, then reopened. The fourth criterion, a probe that retrieval binds the right ruling, fails and needs SEL-003, which you parked as poor value at about 11M tokens. | 13 Oct | A decision on the fourth criterion |
| Seldon | 19 tasks since 1 Oct; 12 open issues. Running now: DESK-002R, with Parts A and B merged at 01:37Z and Parts C and D next. | 17 Oct | DESK-002R finishing |

## 2. Where the week's effort went

**Dispatched sessions, 10 to 17 October: 8.56M tokens.**

| Project | Tokens | Share |
|---|---|---|
| ai-readiness-kg | 5.05M | 59% |
| Seldon tooling | 2.75M | 32% |
| squiddy | 0.76M | 9% |

- **ai-readiness-kg's own judge and critic calls add 6.15M more,** 4.81M of it on Fable. That is why Fable ran dry.
- **Sessions that stopped without finishing used 1.14M,** 13% of the dispatched total.

**The dispatchers mostly could not launch.**

| Since 10 October | Seldon | squiddy |
|---|---|---|
| 5-minute checks | 1,832 | 1,911 |
| Launched work | 9 | 2 |
| Refused | 489 | 308 |
| Crashed | 49 (47 during a Neo4j outage) | 1 |

- **Longest stalls:** Seldon 36 hours (12 to 14 Oct) on one uncommitted file; squiddy 19 hours (15 to 16 Oct) on four causes in turn.
- **No human edit caused any of it.** Every refusal for an unclean working tree came from the system's own uncommitted writes.

## 3. Why it went this way

Five causes, each with the practice that names it. These citations are from memory and not yet fetched. Their impact is low, since they frame a plan rather than support a finding.

1. **Effort went to a non-constraint.** Goldratt's theory of constraints: a system's output rises only when its constraint improves; work elsewhere adds inventory, not throughput.
   - This week's outcomes were constrained by three things: your decisions on the summary and the Arnold ceiling, and the Fable quota.
   - The commit and dispatch plumbing that absorbed a third of the spend sits off that path, except where it costs you pastes and stalls.
2. **One defect class was fixed one member at a time.** Shewhart and Deming separate special causes, fixed case by case, from common causes, which only a change to the system removes.
   - The commit-gate chain has a common cause. Several automatic writers change tracked files, and one global gate (the clean-tree check) refuses all work whenever any of them leaves something uncommitted.
   - DISP-c7, SEL-006, DESK-001 and DESK-002 each taught one more writer to commit itself, and then the next writer surfaced.
   - DN-046 showed the right move on the squiddy side: name the class and close it in one task.
3. **Many controls were built at once and debugged in production.** Gall: a complex system that works evolved from a simple system that worked. Perrow: tightly coupled, interactive systems fail in ways no single component explains.
   - In ten days (7 to 16 October) Seldon gained worktree dispatch, a model registry, the prior-art gate, a commit hook, four inspection stations, registration commits and decision-register checks.
   - The coupling is tight by design. One uncommitted file stops every task, and one station that checks the wrong tree halted a correct session (DESK-002).
4. **Rulings were written on unverified diagnoses.** There were four Desktop errors this week, each costing a cycle:
   - DN-047 took SQ-015's diagnosis as measured, when the failing stage's own record said otherwise.
   - SQ-016 shipped with a guessed path.
   - I registered R-206 with a hash over the wrong bytes.
   - I wrote DESK-002 without knowing its checks run against main.
   The rule already exists (verify against the primary record first). It was not applied.
5. **The live control became the finish line.** Using arnold's stuck admission as the live test was right for finding defects; it produced four rulings (DN-044, DN-046, DN-047, DN-048).
   - But a test that fails one layer deeper each time is a defect finder, not a finish line, and each run spent its single allowed resume.
   - The kit's own failure message names the way out that was never taken: restore the snapshot and admit the document fresh.

## 4. What was done tonight

- **SQ-016 re-issued.** I found SQ-016's wrong premise path and re-issued it as SQ-016R. That run shipped R-206 (resume in ledger order) and established the real cause of the stuck admission: the drift check excluded the admission's own write, which a later export already carried.
- **DN-048 written, and SQ-017 with it.** Ruling R-207 says every export records the ledger position it replayed, and the drift check compares exactly that prefix. The note is grounded in ARIES log sequence numbers and in the projection-checkpoint practice of the eventsourcing library and KurrentDB. It passed the prior-art gate (verdict 89705eb8).
- **The registration gap reproduced, then routed to a fix.** Registering SQ-017 failed the same way DN-047's registration did, so I wrote DESK-002 to fix it. DESK-002 halted on a false stop. DESK-002R re-issued it with merge-before-check and is running.
- **Seldon issues filed:** 5c689098, c5e0f12c, 5bfc2788, 59b2db84, 70bf1a21.

## 5. The plan

**Assumption**, stated per your rule: product outcomes come first this week, in the order ai-readiness-kg working group, then the Arnold evidence graph. Squiddy and Seldon get only fixes that block those. Override if the order is wrong.

**Stop rules for the week**

- One task in flight per repository. No new process machinery in Seldon until DESK-002R and the class fix below are done.
- A live test gets two attempts. If arnold's admission is still open after SQ-017, it is restored from its snapshot and admitted fresh, and the failing case becomes a regression fixture instead of a gate.
- Any diagnosis a ruling rests on is checked against the failing record before the ruling is written.

**Sequence**

1. **Tonight, automatic.**
   - DESK-002R finishes Parts C and D, and Part D registers SQ-017.
   - squiddy's dispatcher then runs SQ-017, estimated at 0.35M.
   - Nothing for you to do. If DESK-002R halts again, section 7 has the hand-run commands.
2. **Saturday, you, about 30 minutes.**
   - Read INSTRUMENT.pdf and PAGE_TWO_VERDICT.pdf in ai-readiness-kg and say what page two is.
   - Then one rebuild task produces summary v4, with Fable restored. Its dispatcher has to be switched back on first.
3. **Weekend, ai-readiness-kg.** Render READINESS_BRIEF as a PDF for the working group; today it exists only in Word and PowerPoint.
4. **Early week, squiddy.**
   - Settle R-186's fourth criterion. My default: move the retrieval probe to the SEL-003 track and declare the exit on the three measured criteria, because the probe tests Seldon's retrieval, not squiddy's admission.
   - Then return to the Arnold evidence graph: a design note on the demand-test miss (which questions failed, and why), and your ceiling decision on the paused pilot.
5. **Midweek, Seldon.**
   - One design note that closes the class of machine-written state in the working tree: who commits what and when, or whether those ledgers belong in git at all, with prior art. It replaces further per-writer fixes.
   - Fold in 02d52bc4 (stations check the session's branch) and 59b2db84 (a database outage becomes a refusal with an alert, not a silent crash).
6. **Hygiene, one cheap task.** squiddy has 61 open issues, and 28 of them say "fixed" in their own text. Verify each and close it.

## 6. Decisions only you can make

1. Page two of the executive summary, a deliverable under your name.
2. The Arnold evidence pilot ceiling: raise it to the projected 5.07M, or narrow the pilot.
3. Whether SEL-003 (about 11M tokens) ever runs. If not, my default on R-186 stands.
4. Rotating the GitHub token stored in claude_desktop_config.json. It has been open since 20 September, and moving it out of the config waits on the rotation.
5. Confirming or changing the product order in section 5.

## 7. If a dispatcher fails again: running by hand

Stop the repository's dispatcher first, so it cannot launch the same task alongside you:

- touch `.seldon/DISPATCH_STOP` in the repository;
- delete it when you are done.

**SQ-017 in squiddy.** Do this only after DESK-002R has merged its Part A, and only if Part D did not register SQ-017.

```
cd ~/GitHub/squiddy
seldon cc register cc_tasks/2026-10-16_SQ-017_dn048_export_ledger_position_arnold_closed.md --allow-untracked
git status
```

The tree should be clean. Then give Claude Code, in squiddy:

```
Read CLAUDE.md, then execute cc_tasks/2026-10-16_SQ-017_dn048_export_ledger_position_arnold_closed.md. Glob and read all sibling *SQ-017*ADDENDUM*.md first.
```

## Sources

**Files**
- squiddy: `docs/evidence/sq010/exit_*.jsonl`, `docs/evidence/sq012/exit_arnold.jsonl`, `docs/evidence/sq016/`.
- arnold: `graphs/arnold-evidence/factory/pause.json` and `corpus/manifest.yaml`.
- ai-readiness-kg: `handoffs/2026-10-15_instrument_audit_verdict_four_of_thirteen.md`, `reports/diagnostic/brief/`, `state/spend_ledger.jsonl`.
- Dispatch logs: `seldon/logs/seldon_dispatch.log`, `squiddy/logs/squiddy_dispatch.log`, and the per-session logs under each repository's `logs/dispatch/`.
- The open issue and task counts come from the four project graphs, queried 17 October.

**Literature** (from memory, not yet fetched)
- E. M. Goldratt and J. Cox, *The Goal*, 1984.
- W. A. Shewhart, *Economic Control of Quality of Manufactured Product*, 1931.
- W. E. Deming, *Out of the Crisis*, 1986.
- J. Gall, *Systemantics*, 1975.
- C. Perrow, *Normal Accidents*, 1984.
