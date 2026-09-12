# CC Task: AD-030 names, supersession syntax, incremental re-ingest, constraint backfill

**Date:** 2026-09-12
**Governing docs:** `docs/design/AD-030_governed_documents_as_graph_content.md`; `docs/design/AD-030_implementation_findings_002.md` (rulings AD-030-R20 to R24). Read both in full, plus `AD-030_implementation_findings_001.md` and `cc_tasks/2026-09-12_ad030_findings_reconcile_RESULT.md` sections 6 and 7.
**Repos:** seldon (`/Users/brock/GitHub/seldon`) and squiddy (`/Users/brock/GitHub/squiddy`, pinned at `governed/squiddy.pin`).
**Autonomy:** L4. Commit, merge to main, push in both repos, bump `governed/squiddy.pin` to the new Squiddy commit, close the Seldon task named in the registration of this file. Decide, log the grounding in the RESULT, proceed.
**Addenda:** Glob and read all sibling `*ADDENDUM*.md` files before starting.

---

## Steps

1. **Incremental re-ingest, Squiddy side (AD-030-R22).** In the kit's assess stage, compare the manifest's recorded sha256 against the file on disk. An `admitted` entry whose hash moved is admissible again. The write stage appends updated node and edge events for that document only; projection merges last-write-wins by key (the existing `latest_by_key`). Children absent from the new extraction (sections, rulings, passages) are emitted as retired for that document, matching Seldon's retire-not-delete. Generic kit behaviour; no Seldon awareness (AD-030-R10). Tests: an edited admitted document re-extracts alone; an unchanged one is skipped; a removed ruling is retired not deleted; an unrelated document's events are untouched. Bump the kit version and record the new commit.

2. **Incremental re-ingest, governed side.** `make -C governed admit ID=<doc_id>` on an edited admitted document must complete in single-document time and leave `seldon verify --strict` at exit 0 after `seldon governed sync`. Measure wall time for one edited file versus the full sweep and register both as Results. `governed/reset.sh` stays as the reset path and its header comment says so.

3. **`Name:` header field (AD-030-R20).** Recipe reads `Name:` from the header block; when present it is the Document `name`. When absent, the existing derivation and tiebreak apply. Findings note 002 carries `Name: AD-030-F002`. Backfill nothing: existing documents keep derived names. `seldon governed status` reports documents whose derived name collided under the tiebreak so the operator can add the field.

4. **Supersession pattern (AD-030-R21).** Ruling-level: `Supersedes AD-NNN-Rn.` sentence-final in ruling text, one or more hyphenated IDs. Document-level: `Supersedes:` header field with document names. Nothing else emits `SUPERSEDES`. Remove the hand-written R17 to R10 edge and confirm the recipe re-creates it once R17's text is re-read; if R17's current wording ("Supersedes the `pyproject.toml` clause of AD-030 R10") does not match the pattern, that is expected and correct: it stays as the one hand-written edge, and the RESULT states so. Do not edit Findings 001.

5. **R16 readings (AD-030-R23, R24).** Confirm `force_patterns` and the label-versus-mention rule shipped in the reconcile task match the ruling text; add a test per clause of R23 if one is missing. Confirm `read_rulings` default excludes `retired` and `superseded`.

6. **Constraint backfill.** `seldon cc constrain --all --dry-run`, review the match set in the RESULT (count of tasks, distribution of edges per task, any task matched by more than eight concept rulings), then run it live. Register `constrained_by_edges_backfill_total` and `tasks_constrained_backfill` as Results.

7. **Catalog and admit** Findings 002 and this task file; after writing the RESULT, admit it too using the step 1 path, not a full sweep. Re-verify all governed counts under R18.

8. Full suite in both repos. `seldon verify --strict` exit 0.

## Success Contract

| Deliverable | Verification | Expected |
|---|---|---|
| Incremental re-ingest | edit one admitted `.md`, `make -C governed admit ID=<id>`, `seldon governed sync`, `seldon verify --strict` | exit 0, no full sweep, ledger event count grows by that document's delta only |
| Timing | Results `governed_reingest_single_seconds`, `governed_reingest_full_seconds` | both verified; single well under full |
| Name field | `MATCH (d {artifact_type:'Document'}) WHERE d.path CONTAINS 'findings_002' RETURN d.name` | `AD-030-F002` |
| Supersession | `MATCH (a {artifact_type:'Ruling'})-[:SUPERSEDES]->(b) RETURN count(*)` | 1 (R17 to R10), hand-written or recovered as stated in RESULT |
| Backfill | `MATCH (t:ResearchTask)-[:CONSTRAINED_BY]->() RETURN count(DISTINCT t)` | > 13 |
| Pin | `governed/squiddy.pin` | new Squiddy commit, `make -C governed check-squiddy` passes |
| Rulings | AD-030 10, Findings 001 9, Findings 002 5, every RESULT and task file 0 | as listed |

## Scope boundaries

- Do not edit AD-030 or either findings note. Findings go in the RESULT.
- DI-005 unchanged.
- Zero model calls.
- Arnold corpus out of scope; it is the next task, blocked on step 1.
- No second closeout term.
