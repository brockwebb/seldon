# SUB-RESULT — `42be368d` recoverability and replay

**Parent task:** `cc_tasks/2026-09-04_seldon_open_defect_closeout.md` step 1
**Date:** 2026-09-04
**Worktree:** `open-defect-closeout`, base SHA `56a28662d9ebae07e20c021a89fb9add9cc39bf5`
**Executed by:** a lane subagent (stalled partway) + the integrator, who verified its state and finished the live steps

---

## 0. Lane interruption and state recovery

The lane stalled at the message "now running the live migration" — the worst point to lose an agent. State was assessed before anything else, rather than assumed:

- **Main checkout's log was intact**: 1757 lines, still 9 without `event_id`, **zero** `legacy_event_id_assigned` records. The live migration had not run.
- **Worktree's log**: 1766 lines = 1757 + 9 appended assignment records, with the 9 legacy lines **un-rewritten**. Append-only was respected.
- **Live graph untouched**: 260 artifacts / 61 relationships, unchanged.
- **No scratch or replay databases leaked**; 30 databases, same as before.

The work was coherent and complete except for the live steps, which the integrator finished. Nothing was discarded and nothing was re-run blindly.

## 1. What shipped

| Item | Status |
|---|---|
| (1) Deterministic ids for legacy lines, by append | Done |
| (2) `read_events` tolerates the legacy shape | Done |
| (3) `seldon verify` replay check | Done, opt-in |
| (4) Audit all databases | Done |

New modules: `seldon/core/legacy_events.py`, `seldon/core/replay_check.py`, `seldon/core/projects.py`, `seldon/commands/events.py`. New tests: `test_legacy_events.py`, `test_replay_check.py`, `test_projects_discovery.py`, `test_verify_event_log.py`.

### The id recipe

`legacy-{ordinal:06d}-{sha256(canonical_json(record))[:32]}`

The **parsed object** is hashed, not the raw line, so reformatting the file yields the same id — the id identifies the event's content, not its serialisation. Ordinal is the 1-based index among successfully-parsed records.

Collision with a real uuid4 is impossible **structurally, not probabilistically**: a uuid4 is 36 characters and contains only `[0-9a-f-]`; a legacy id is 46 characters and begins with the literal `legacy-`, whose `l`, `g` and `y` are not hex digits. Either property alone suffices.

**Determinism was proven across two different files**, not asserted: the 9 ids derived from the main checkout's log are byte-identical to the 9 assignment records written in the worktree.

```
legacy-000001-da73da372f777668b75dff5ed51830fd
legacy-000002-e4ae156cf8fbf1c4b6b1e7dfcc0a1c34
… (9 total, identical from both logs)
```

That is what makes the merge of this branch equivalent to having run the migration on main.

### `read_events` tolerance

`read_events` derives the same id on **every** read, so recoverability is restored whether or not the migration has run. The appended records are an audit trail and tamper detector, **not** a lookup table `read_events` depends on — a lookup table would force a two-pass read and make recoverability contingent on a migration having been run, which is the fragility being removed.

Confirmed live: `read_events` now succeeds on the worktree log (1766 events) **and** on the main log (1757 events), which still carries the 9 legacy lines and no assignment records.

The real duplicate check is unweakened — two genuinely duplicated uuid4s still raise.

### `legacy_event_id_assigned` and `sync.py`

Added explicitly to `_AUDIT_ONLY_EVENT_TYPES`, alongside `paper_fix` and `link_case_migrated`. This was a deliberate decision, not an oversight: `sync.py` silently skips unknown event types, which the 2026-09-03 sweep recorded as the reason a bespoke migration event would "vanish on replay". The record is provenance about the log, not a graph mutation, so audit-only is correct — but it had to be **stated** rather than defaulted.

### Replay-check scope

**Opt-in, deliberately.** `seldon verify` is run before every commit; replaying every project's log into a scratch database on each run would make the gate unusable. So:

- `seldon verify` always runs a cheap **readability** check (check 10) — reading the log proves it is legible.
- `seldon verify --replay` adds this project's replay (check 11).
- `seldon events replay-check --roots ...` is the deliberate all-project sweep.

The scratch database is created per run and dropped after; **no project database is ever written to** — each live graph is read only, to fingerprint it.

## 2. Two defects found in the new check, and fixed

The check as first written produced findings that were technically true and practically useless. Both were fixed by the integrator, with tests.

### 2a. Raw node counts over-reported by 23,000

`fingerprint_graph` counted every non-internal node. `seldon-ai-readiness-kg` stores a ~23k-node knowledge graph alongside its Seldon artifacts — content that was never event-sourced and never claimed to be. The check reported:

```
node count: live 27488, replayed 4144
```

for a project whose actual artifact divergence was **two artifacts**. A check that renders a 2-artifact problem as a 23,000-node failure stops being read, and an ignored check is worse than no check because it launders the real findings underneath it.

Fixed: counts are artifact-scoped, and non-artifact nodes are reported once as context (`note:`), not as a mismatch. `matches` was already artifact-scoped, so the verdict was never wrong — only the reporting.

### 2b. Inherited ontology terms counted as unrecoverable state

Every project reported exactly "2 artifact(s) in the live graph that replay does not produce". Diagnosed rather than accepted: they are `OntologyTerm` nodes — the two junk `leibniz-pi` terms from the 2026-09-04 sweep.

`OntologyTerm`s are replicated from the `seldon-ontology` master by `seldon ontology sync` (AD-017) and **cannot be created locally at all** — `create_artifact` refuses when `inheritance: read-only`. That is precisely why no local event exists. Their recoverability is real and is provided by re-syncing from master, not by replay.

Fixed via `INHERITED_ARTIFACT_TYPES`, excluded from the comparison and reported as context. **Effect: 5 projects went from "fails" to "reproduces exactly".** Those were pure false positives; 13 projects each carried 2 of them.

## 3. Audit across all projects (item 4)

14 projects found on disk. (The "30 databases" figure counts *databases*; most have no project directory.) Read-only for every project.

| Result | Projects |
|---|---|
| Legacy records with no assignment | **1** — `seldon-self` (9 legacy, 0 assigned) |
| Clean | 12 |
| Unreadable (no `seldon_events.jsonl`) | 1 — `services` |

`seldon-self` is the only project with the defect. No other project was written to; a defect in someone else's project is theirs to migrate.

## 4. Replay results across all projects (item 3)

Full capture in `replay_check_full.txt`. **8 of 14 do not reproduce cleanly; 5 reproduce exactly; 1 skipped** (no `neo4j.database` configured).

| Project | Result |
|---|---|
| TickBiteRisk | OK — 254 events, 118 artifacts / 39 rels exact |
| book_responsible_ai | OK — 311 events, 82 / 98 exact |
| census-web-concept-inventory | OK — 192 events, 45 / 36 exact |
| federal-survey-concept-mapper | OK — 126 events, 49 / 36 exact |
| sas2graph | OK — 24 events, 14 / 1 exact |
| usai-harness | OK — 249 events, 65 / 36 exact |
| leibniz-pi | 1 replay-only artifact, 2 replay-only rels |
| ai-readiness-kg | 20 rels written outside the event path |
| ai-workflow-design | 11 replay-only artifacts, 15 rels outside the path |
| arnold | 8 replay-only BuildRuns |
| brock-projects | 2 unrecoverable, 16 replay-only, 14 replay-only rels |
| icsp_notebook | 1 unrecoverable, 1 replay-only, 1 rel outside the path |
| seldon-self | 2 unrecoverable, 18 state mismatches, 5 rels outside the path |
| services | SKIP |

**Recoverability is a declared guaranteed property and it does not hold for most projects.** That is the headline finding of this task. Per the task's own instruction, mismatches were **diagnosed, not reconciled** — no live graph was edited to make a check pass.

### Diagnosis of `seldon-self`'s 18 state mismatches

The dominant pattern is `live` ahead of `replayed`:

```
ResearchTask : live='completed' replayed='proposed'   (6)
AgentRole    : live='active'    replayed='proposed'   (6)
Workflow     : live='active'    replayed='proposed'   (3)
```

State transitions were applied to the graph with **no `artifact_state_changed` event written** — the same class of un-evented write that the 2026-09-03 sweep found as 4 raw-Cypher edges.

One case is inverted and worse: `5d15c856 (DesignNote): live='proposed' replayed='final'`. Replay produces `final`, which **is not a legal `DesignNote` state** — `research.yaml` allows `proposed → active → {stale, deprecated}`. So an event exists in the log carrying an illegal `to_state`, and it was applied on replay without validation. Recorded as a finding; not fixed here.

### Unknown event types skipped during replay

Replay emitted `Unknown event_type ... — skipped during sync` for `morning_brief_feedback` (×4), `headless_mcp_wiring`, `headless_mcp_wiring_addendum`. Bespoke event types written by other tooling are silently dropped by `sync.py`, which guarantees replay divergence for any project using them. This is the same silent-skip mechanism that made the audit-only decision in §1 necessary, seen from the other side.

## 5. Premises contradicted by live state

1. **"30 DBs" is a database count, not a project count.** 14 projects exist on disk; the audit and replay sweep necessarily cover those.
2. **The legacy lines lack `timestamp` too**, not only `event_id` — the task named only the id. They are pre-envelope flat records with no envelope at all.
3. **The failure is `DuplicateEventError`, not a missing-field error.** Two records whose id is `None` looked like a collision, so the log failed on the *duplicate* check rather than anywhere obvious.
4. **Recoverability is broken far beyond `seldon-self`.** The task framed this as a `seldon-self` defect; it is systemic.

## 6. Not done, deliberately

- **No other project's log or graph was migrated or repaired.** The task says audit and report; migrating another project's history is that project's decision.
- The un-evented writes found in 8 projects are reported, not reconciled. Editing either side to make the check pass would destroy the evidence of what diverged.
