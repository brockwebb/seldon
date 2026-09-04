# RESULT — Seldon open-defect closeout

**Task:** `cc_tasks/2026-09-04_seldon_open_defect_closeout.md`
**Date executed:** 2026-09-04
**Executed by:** CC (integrator) + five lane subagents
**Worktree:** `open-defect-closeout`, base SHA `56a28662d9ebae07e20c021a89fb9add9cc39bf5`
**Closes:** `42be368d`, `0977c79a`, `c9fdef46`, `3376805b`, `f6b32bbe`
**Blocked, not closed:** `1581c3ec` — see §5
**Sub-RESULTs:** `cc_tasks/2026-09-04_{recoverability_replay, small_defects, resolver_options_and_placeholder, replica_sync_all, si09_removal_condition}_SUBRESULT.md`

---

## 1. Test counts

| | Count |
|---|---|
| Baseline at worktree branch point | **1180 passed** |
| Final (serial, two consecutive runs) | **1444 passed, 0 failed** |
| Net new | **+264** |

Scope rule honoured: these six graph tasks and nothing else. The April/May design backlog stays open.

## 2. `42be368d` — recoverability

Shipped: deterministic legacy ids by **append** (`legacy-{ordinal:06d}-{sha256(canonical_json)[:32]}`), `read_events` tolerance, an opt-in replay check, and a fleet audit. Collision with a uuid4 is impossible *structurally* — 46 chars vs 36, and `legacy-` contains non-hex letters. Determinism was **proven across two files**: the 9 ids derived from the main checkout's log are byte-identical to the records written in the worktree.

`read_events` now succeeds on both logs. The derivation runs on every read, so recoverability does not depend on the migration having been run; the appended records are an audit trail and tamper detector, not a lookup table.

`legacy_event_id_assigned` was added explicitly to `_AUDIT_ONLY_EVENT_TYPES` — a deliberate decision, because `sync.py` silently skips unknown types, which is exactly how a bespoke migration event would vanish on replay.

**The lane stalled mid-task**, at "running the live migration". State was verified rather than assumed: main's log was intact (1757 lines, 9 unassigned), the worktree's had the 9 records appended with legacy lines un-rewritten, the live graph and databases untouched. The work was coherent; the integrator finished the live steps.

### Two defects found in the new check, and fixed

1. **Raw node counts over-reported by 23,000.** ai-readiness-kg holds a ~23k-node knowledge graph that was never event-sourced; the check rendered a 2-artifact divergence as `live 27488, replayed 4144`. A check that loud stops being read, and an ignored check launders the real findings under it. Counts are now artifact-scoped; non-artifact nodes are stated once as context.
2. **Inherited ontology terms counted as unrecoverable.** Every project reported exactly "2 unrecoverable artifacts" — `OntologyTerm`s, which `seldon ontology sync` replicates from master and which `create_artifact` **refuses** to create locally, so no local event can exist. Excluded via `INHERITED_ARTIFACT_TYPES`. **Effect: 5 projects moved from "fails" to "reproduces exactly."**

### The measurement

14 projects on disk (the "30 DBs" figure counts *databases*). Only `seldon-self` carried the legacy defect. After both corrections: **8 of 14 do not reproduce, 6 reproduce exactly, 1 is not a Seldon project.**

**Recoverability, a declared guaranteed property, does not hold for most projects.** Per the task, mismatches were diagnosed and never reconciled — no live graph was edited to make a check pass, and no other project's history was touched.

### Diagnosis of seldon-self's 18 state mismatches

Split cleanly in two, by inspection of the log:

- **9 are causally misordered.** All nine legacy lines (indices 0–8) are `artifact_state_changed` records that sit **before** the `artifact_created` events for the same artifacts (indices 30–38) — 6 AgentRoles and 3 Workflows. Replay calls `change_state` on a node that does not exist yet (a no-op `MATCH`), then creates it as `proposed`. So the legacy block is not merely missing ids; it is out of causal order, and those 9 artifacts **cannot** be replayed to their live state from this log. Correctly reported as unrecoverable.
- **9 are genuine un-evented writes** — 6 ResearchTasks and 3 DesignNotes with **no** `artifact_state_changed` events at all, yet live states ahead of `proposed`.

One event carries `to_state='final'` for a `DesignNote`, which is **not a legal state** — `research.yaml` allows `proposed → active → {stale, deprecated}`. The log contains a transition the state machine forbids, applied on replay without validation. Recorded, not fixed.

Replay also emitted `Unknown event_type … — skipped during sync` for `morning_brief_feedback` (×4), `headless_mcp_wiring`, `headless_mcp_wiring_addendum` — bespoke types written by other tooling, silently dropped, guaranteeing divergence for any project that uses them.

## 3. `0977c79a` — small defects

All four items shipped. Master epoch **4 → 5 → 6**, exactly twice, one `ontology_ingested` event each, snapshotted before and after every live write.

- **(a)** 6 previously-unparsed terms ingested (5 `instrument:*`, 1 `crosscutting:bounded_agency`). The **third section was deliberately not minted**: `### Core Construct: Context Window` defines a term already in the graph, and `_render_glossary` keys one entry per `name`, so a second node would trade a silent absence for a silent corruption. Enforced by `test_context_window_is_not_minted_twice`, not left as a comment.
- **(b)** `python -m seldon` works, with a test asserting the shim's command set equals `cli.main.commands` so it cannot drift into a second CLI.
- **(c)** Both halves were required, and the integrator's framing of "just fix the config" was wrong: `/Users/brock/GitHub/seldon/ontology/` **exists** when seen from a worktree — it is the main checkout — so a fallback keyed on absence never fires. The symptom was a *wrong answer*, not an error.
- **(d)** `_term_content_hash` widened behind `_TERM_HASH_VERSION = 2`; dry run **109 rows**, live matched, epoch 5 → 6, replicas re-sync. Justified: the v1 hashes asserted "unchanged" about content the graph never verified. A third ingest is a clean no-op.

Found and deliberately not fixed: `source_vocabulary` already held **four different values** across 105 terms — three absolute dev paths from three checkouts, one a dead worktree. Fixing it means a third mass update and a third epoch bump, which would have destroyed the attribution this task was asked to keep legible.

## 4. `f6b32bbe` + `3376805b` — resolver options and the placeholder

`resolve_references` gained `mark_proposed` and `value_formatter`; defaults are byte-identical to prior behaviour. `{{result:<NAME>:value}}` is no longer a token while `{{result:G1_x:value}}` is — a test that also pins the uppercase amendment reaching `REFERENCE_PATTERN`, not just `result register`. The ai-readiness-kg shim's two workarounds are now unnecessary and its pre-filter can go.

**All three token types share the grammar**, on evidence: a `cite` token names a *Citation artifact*, not a BibTeX key — the key lives in that artifact's `bibtex_key` property, which is what SI-07 reads — so narrowing the token grammar constrains no BibTeX key. The defect was never `result`-specific.

**The task's "import it" instruction was impossible**: `seldon/commands/result.py` imports `REFERENCE_PATTERN` from `seldon/paper/build.py`, so an eager import back is a hard cycle failing in both directions (verified empirically). The lane shipped a lazy wrapper inside its own file with the correct fix as its removal condition; the integrator then **did** that fix — `RESULT_NAME_PATTERN` hoisted to `seldon/core/naming.py`, a leaf module importing nothing from Seldon. The wrapper collapsed back to a plain `re.compile`, `DEFINITION_POINT` moved with it, and both import orders verified. The workaround is gone, not documented.

## 5. `1581c3ec` — SI-09 removal: BLOCKED, not closed

Fleet-wide measurement with one instrument (`seldon paper check-units-fallback`, added for this): 14 project dirs, 107 tracked files, 535 result tokens, **SI-09 resolutions = 0 everywhere**, including ai-readiness-kg re-measured with Seldon's own resolver rather than trusting its shim.

**Removal is still blocked, and that is the correct outcome.** The condition in `build.py` has two conjuncts — `migrate-names` run against *every* project graph **and** no build emitting SI-09. The second holds; the first does not:

| blocking project | Results | named | **unnamed** |
|---|--:|--:|--:|
| icsp_notebook | 346 | 0 | **346** |
| TickBiteRisk | 61 | 0 | **61** |
| brock-projects | 2 | 0 | **2** |
| sas2graph | 2 | 1 | **1** |

**410 unnamed Results in 4 of 13 graphs.** Those four score zero only because three have no token-bearing prose and the fourth's one file has no grammar-valid token — the zero means "nobody wrote the prose yet", not "migration complete". The first `{{result:...}}` any of them writes lands on an unnamed Result: today a non-fatal SI-09 naming the fix, post-removal a hard SI-01 with no transitional path.

Not one SI-09 line was deleted. The task is transitioned to **`blocked`** with the blockers named, exactly as the parent task file directs ("note in the task that removal is blocked by named projects").

To unblock: run `migrate-names` in those four to zero unnamed, re-run the instrument, then delete the fallback **and the instrument** in one commit.

## 6. `c9fdef46` — replica sync

`seldon ontology sync --all`, dry-run by default, per-database report, re-runnable. **All 13 real replicas now at epoch 6 / 111 terms / 109 active / 2 deprecated.** The two junk `leibniz-pi` terms are `deprecated` everywhere. A second `--all --apply` reports `Synced 0 replica(s); 13 already current.`

Discovery is by `_OntologyReplicaMeta` **marker, never by name prefix** — the prefix is wrong in both directions here: `seldon-ai4stats`, `seldon-arnold`, `seldon-leibniz-pi`, `seldon-sas2graph` and `seldon-test` carry it and hold no replica marker. Masters are excluded twice, by configured name and by `_OntologyMeta` marker.

**`seldon-test-project` was NOT dropped.** No `seldon.yaml` names it, but the repo does: `tests/testdb.py` derives `TEST_PROJECT_DATABASE` which resolves to exactly that name under the documented `SELDON_TEST_DATABASE=seldon-test` serial-run override; it was last written 2026-09-04T15:06Z with contents matching that path; it is in `observability_collect.py`'s `EXCLUDED_DBS` and asserted never-droppable in `test_testdb.py`'s `PROTECTED_NAMES`. Per the task's own stop rule, reported instead of dropped.

## 7. Integration criterion not fully met, and why

The task requires "`seldon verify` clean including the new replay check."

- **`seldon verify` is clean** — exit 0, all checks pass, including the new `Event log` and `Relationship types` checks.
- **`seldon verify --replay` fails**, reporting seldon-self's 2 unrecoverable artifacts, 18 state mismatches and 5 un-evented relationships.

That failure **is the correct output**. Making it pass would require either fabricating compensating events for state the log never recorded, or rewriting the causal order of the legacy block — both of which violate the append-only guarantee this task exists to defend, and both of which the task explicitly forbids ("Legacy lines are never rewritten"; "diagnose the un-evented write; do not reconcile"). The check is measuring a real broken property, and the property is broken.

This is why the replay check is opt-in rather than part of the default gate: a pre-commit gate that cannot go green until a historical defect is repaired would simply be disabled.

## 8. Premises contradicted by live state

1. **"30 DBs" is a database count**; 14 project directories exist, 13 of them real Seldon projects.
2. **The legacy lines lack `timestamp` too**, not only `event_id`; and the failure mode is `DuplicateEventError` (two `None` ids read as a collision), not a missing-field error.
3. **The legacy lines are also causally misordered** — state changes preceding their own creates. The task described an id problem; it is an ordering problem as well.
4. **Recoverability is broken fleet-wide**, not just on `seldon-self`.
5. **`c9fdef46`'s epoch figures were stale on arrival**: master was at 6, not 3; ten replicas were at epoch 3, not thirteen.
6. **`3376805b`'s "import it" instruction was impossible** — circular import.
7. **`0977c79a`'s (c) could not be fixed by config rewrite or fallback alone**; both were required.
8. **`seldon.yaml` is not a reserved filename** — `webdesktop/services/seldon.yaml` is a service definition for a service named "seldon". Fixed with a shape check in `load_project_ref`, distinguishing "not ours" from "ours and broken".

## 9. Findings recorded, not fixed

1. An event in `seldon-self`'s log carries `to_state='final'` for a `DesignNote` — a state the machine does not define — and replay applies it without validation.
2. Bespoke event types (`morning_brief_feedback`, `headless_mcp_wiring*`) are silently skipped by `sync.py`, guaranteeing replay divergence wherever they are used.
3. 8 projects hold graph state their logs cannot rebuild; the specific artifacts and relationships are listed per project in `replay_check_full.txt`.
4. `source_vocabulary` on master holds four different absolute dev paths; should be relative to the ontology root.
5. 410 unnamed Results across 4 project graphs (§5).
