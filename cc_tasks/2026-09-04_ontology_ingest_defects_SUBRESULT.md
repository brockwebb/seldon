# SUBRESULT — `seldon ontology ingest` defects (Lane 2)

**Date:** 2026-09-04
**Worktree:** `/Users/brock/GitHub/seldon/.claude/worktrees/defect-fixes-ad028`
**Graph task:** `9ae4b245` (2026-09-03 defect sweep, Lane B + RESULT §9.2)
**Status:** both defects fixed and tested. The live orphan-clearing step was
**deliberately not executed** — its stated precondition is false (see §5).

---

## 1. What shipped

| File | Change |
|------|--------|
| `seldon/commands/ontology.py` | Compare-first ingest, deprecation pass, sync state propagation, event-store override |
| `tests/test_ontology.py` | Two tests that encoded the defect rewritten; ingest event-store isolated from the repo log |
| `tests/test_ontology_ingest_lifecycle.py` | New — 25 tests (11 pure-plan, 11 ingest, 3 sync) |
| `CLAUDE.md` | Shared Ontology section documents epoch semantics and `--deprecate-missing` |

### Defect 1 — compare first, bump only on change

`ingest_command` no longer calls `_increment_epoch` before it knows anything.
The flow is now: parse → index → read master state → `build_ingest_plan` →
decide → (only if the plan is non-empty) bump the epoch and apply.

- `build_ingest_plan(parsed_index, master_terms, parsed_rels, master_rels)` is a
  **pure function** returning an `IngestPlan` dataclass. That is what makes
  "compare first" testable without a database — 11 of the new tests are pure.
- `IngestPlan.has_changes(deprecate_missing)` is the single gate on the epoch.
- A no-op ingest: no epoch bump, no `ontology_ingested` event, no replica
  staled, and an explicit message —
  `No changes: 100 terms already current. Master epoch stays 3; no event written.`
- `--dry-run` now reads real master state (with `allow_missing=True`, so it never
  creates the database it inspects) and prints the same plan the live run would
  execute, including whether the epoch would move.

Two secondary traps fixed while in here, because either one would have
re-introduced the same "every run looks changed" behaviour:

1. **Relationship counting.** The old code counted `MERGE` result rows, which are
   returned whether or not the edge was created. Change detection now diffs the
   source's relationship triples against master's.
2. **Unwritable relationships.** A source relationship naming a term that exists
   in neither the source nor master can never be created. Counting it as a
   pending change would bump the epoch on every future run forever. It is
   reported as a warning and excluded from the plan.

Also: `state` is no longer written by the update path. `_term_to_props` always
sets `state: "active"`, so an update of a non-active term was an unvalidated
state transition performed by a markdown file. State is lifecycle; the source
vocabulary has no authority over it.

### Defect 2 — deprecation pass

- A master term absent from the parsed source and in state `active` is listed in
  `plan.to_deprecate`.
- With `--deprecate-missing`, each is transitioned through
  `seldon.core.artifacts.transition_state`: the domain state machine validates
  `active -> deprecated`, an `artifact_state_changed` event is appended, and only
  then is the node touched. By event, never by direct mutation. The
  `ontology_ingested` event for the run also carries `deprecated_terms` and
  `deprecated_term_ids`.
- Terms absent from the source in a state with no legal edge to `deprecated`
  (e.g. `stale`) are reported and left alone rather than force-set.
- A source term that master holds as `deprecated` **aborts the whole ingest
  before any write**, because `deprecated` is terminal in the `OntologyTerm`
  state machine (`seldon/domain/research.yaml`: `deprecated: []`). Silently
  reactivating it would be an illegal transition; partially applying the rest of
  the run and then failing would be worse. The message names the term_ids and
  says to remove them from the source or issue new term_ids.
- Backstop: an ingest that parses **zero** terms is refused. Both current parsers
  already raise on an empty parse; this guards the next one, which would
  otherwise be able to empty a database every project reads.
- Duplicate `term_id` across vocabulary files is now an error. Previously the
  later file silently won.

---

## 2. The flag shape, and why

**`--deprecate-missing`** (default off), alongside the existing `--dry-run`.

- **Opt-in, because the operation is terminal.** `deprecated` has no outgoing
  edge. An accidental deprecation cannot be walked back through the state
  machine — it needs graph surgery. Anything irreversible gets an explicit act.
- **Default is report-only, not silence.** Plain `ingest` lists every orphan by
  term_id and name and prints the exact command to retire them. The operator
  discovers the orphans by running the safe command; discovery does not require
  arming the destructive one.
- **The orphan list alone never bumps the epoch.** `has_changes()` counts
  `to_deprecate` only when the flag is set. Otherwise a repo with orphans could
  never have a no-op ingest — defect 1 through the back door.
- **`--dry-run --deprecate-missing` is the rehearsal.** It prints the exact term
  list and `epoch would move N -> N+1`, and writes nothing.
- **Rejected: a `--yes`/`--force` confirm prompt.** Ingest is run from scripts
  and from agent sessions where an interactive prompt is either invisible or
  auto-answered. A flag is the same guarantee and survives non-interactive use.
- **Rejected: deprecate-by-default with an opt-out.** The failure mode being
  guarded is a truncated, mid-edit, or mis-parsed source file. That file looks
  exactly like a legitimate deletion. Defaulting to destruction means the
  degenerate case is the destructive one — and §5 below is precisely that case
  occurring in the wild.

---

## 3. What `sync` does with a newly-deprecated term, and why

Two situations, two different answers:

1. **The replica already carries the term.** The deprecation is propagated: the
   replica term is set to `deprecated`.
   *Why:* the requirement is that a replica can never be left calling a term
   active that master considers dead. The old code compared only
   `content_hash`, and a deprecation does not change content — so the replica
   kept the term `active` indefinitely. State is now replicated whenever it
   diverges from master, independently of the content comparison, and content
   updates no longer carry `state` along implicitly.
2. **The replica never carried the term.** It is *not* created. Counted as
   `skipped_deprecated` and reported.
   *Why:* a dead term that a project never referenced adds no provenance to that
   project and pollutes `seldon ontology list` for everyone who onboards after
   the retirement. Nothing in the project can point at it, so there is nothing to
   keep honest. Projects that *did* reference it keep the term, in `deprecated`
   state, so their existing `references_ontology` edges stay resolvable — the
   record of what the project once relied on is preserved.

Replica state changes go through `change_state` and are summarised in the
`ontology_synced` event (`deprecated_terms`, `state_synced_terms`,
`skipped_deprecated_terms`), matching the pre-existing replica model: replicas
are projections of master, and replay restores them by re-running sync
(`seldon/core/sync.py::_restore_ontology`), not by replaying per-term events.

Note on replay: the master-side `artifact_state_changed` events land in the
Seldon repo's event log. Sync preserves `artifact_id` across master and replica,
so a `seldon rebuild` of `seldon-seldon-self` applies the same deprecation to the
replica, and the post-loop ontology restore re-syncs from master anyway. The two
paths agree.

---

## 4. Live-run evidence

All read-only inspection and both live commands were run from this worktree
against the real `seldon-ontology`. A full JSON snapshot of master (meta, all
105 term nodes, all 36 relationships) was taken **before** anything ran.

**Before:** master epoch **3**, **105** terms, all `active`, 36 relationships.
`seldon-seldon-self` replica: epoch 3, 105 terms, 0 deprecated.

`seldon ontology ingest --dry-run` (live master):

```
Total: 100 terms, 36 relationships across 2 files.
[DRY RUN] Change plan against the master database:
  Create:    0 terms
  Update:    0 terms
  Unchanged: 100 terms
  New relationships: 0
  Would deprecate (needs --deprecate-missing): 5 terms
    - ontology:validity:related:compaction  Compaction
    - ontology:validity:related:context_window  Context window
    - ontology:validity:related:fidelity  Fidelity
    - ontology:validity:related:handoff_document  Handoff document
    - ontology:validity:related:state  State
No changes. Master epoch would stay 3 and no event would be written.
```

`seldon ontology ingest` (live, no flag — the real no-op proof):

```
No changes: 100 terms already current. Master epoch stays 3; no event written.

5 active term(s) in master are absent from the source:
  ... (the same five)
Re-run with --deprecate-missing to retire them (irreversible), or restore them
in the source vocabulary.
```

**After:** master epoch **3**, **105** terms, all `active`, 36 relationships.
A second full snapshot diffed **byte-identical** against the pre-run snapshot.
`seldon_events.jsonl` unchanged across the ingest and the sync (1693 lines, md5
`be8af3a5…` immediately before and immediately after each command; it has since
moved because other lanes write to the same log in this shared worktree).

`seldon ontology sync` (this project only, `seldon-seldon-self`):

```
Already up to date at epoch 3.
```

No event written, no writes. Under the old code the ingest above would have
burned epoch 3 → 4, written a false `ontology_ingested` event, and left this and
every other replica stale.

---

## 5. Premise in the task description contradicted by live state

> "master carries 5 orphan `active` terms from epoch 1 **absent from the
> markdown**"

**Half true, and the false half is the important half.** The five terms are
absent from the *parse*. They are still present in the *markdown*, under
`## Related Terms (Defined Elsewhere)` at
`ontology/validity/VALIDITY_VOCABULARY.md:285` — Context window, Compaction,
Handoff document, State, Fidelity. Each has a definition in the file today.

The cause is a **parser regression**, not a vocabulary deletion:

- `seldon/ontology/parser.py::_parse_related_terms` expects that section to be a
  markdown **table**. It finds the heading, then scans forward for the first line
  starting with `|`.
- The section was rewritten as a definition list (`**Term**` / `: definition`) in
  commit `62d6bdf` ("centralize enforcement — shared ontology + seldon paper
  glossary").
- So the forward scan runs straight past the section and parses the **next**
  table in the file — `## Terms That May Be Promoted from Projects` — as if those
  rows were related terms.

Two consequences, both live in master right now:

1. The 5 genuine related terms stopped being parsed (they became the "orphans").
2. Two junk terms were ingested in their place and are `active` in master and in
   every replica: `ontology:validity:related:log_precision_fitness` and
   `ontology:validity:related:precision_gain_rate`, whose `definition` is the
   literal string `leibniz-pi` — the *Origin Project* column of the wrong table.

**Therefore I did not run the live deprecation pass.** Precondition (b) of the
task ("confirming the 5 orphans are genuinely absent from both markdown files")
is false. Retiring them would have used a terminal, irreversible state to make a
silent parser regression permanent, and would have destroyed five documented
terms because of a formatting change. This is exactly the case the opt-in flag
exists to catch, and it caught it on its first live outing.

**Recommended follow-up (new task, not done here):** fix
`_parse_related_terms` to read the definition-list format and to stop scanning
past its own section. After that fix, the correct live sequence is:

1. `seldon ontology ingest --dry-run` — expect ~5 creates or updates (the real
   related terms return) and exactly 2 deprecation candidates (the junk terms).
2. `seldon ontology ingest --deprecate-missing` — epoch 3 → 4.
3. `seldon ontology sync` per project.

That is a content change to the shared ontology and deserves its own review; it
is a third defect, not part of this task.

---

## 6. Other findings worth a task

1. **`_term_content_hash` is too narrow.** It covers `term_id | definition |
   category` only. A change to a term's `name`, `citations` or `extra` is
   invisible to change detection: the epoch will not move and replicas will
   never see it. Widening the hash was deliberately **not** done here — it would
   mark most of the 105 live terms as changed and force a large, unrelated live
   update in the middle of a defect fix. Should be widened in its own task, with
   the resulting one-off mass update run knowingly.
2. **Ingest never removes relationships.** An edge deleted from the source stays
   in master forever. Live count today is 36 in both, so nothing is pending, but
   the asymmetry with term deprecation is real.
3. **Test runs used to append to the repo's tracked event log.** `ingest` writes
   its events to the Seldon repo's event store (it is a repo-level command, not a
   project one), so every `pytest` run appended real `ontology_ingested` events
   to `seldon_events.jsonl`. Fixed for this lane by
   `SELDON_ONTOLOGY_EVENT_DIR`, which mirrors the existing
   `SELDON_ONTOLOGY_PATH` override and which the ontology tests now set. Other
   repo-level commands may have the same problem.
4. **AD-017 documentation is stale** with respect to this change (epoch is now a
   change counter; deprecation exists). `docs/design/**` is another lane's file
   set, so it was not touched. `CLAUDE.md` was updated instead.

---

## 7. Cross-lane notes

- The three lanes are sharing **one** worktree, not one worktree each. Files
  owned by other lanes (`seldon/commands/result.py`, `verify.py`, `cc.py`,
  `seldon/core/**`, `tests/conftest.py`) changed under me during the session.
- **The stated baseline of "1001 passed" was not what this worktree had.** At the
  start of this lane it was **999 passed, 2 failed** —
  `tests/test_result_registry.py::test_validate_result_name_rejects_invalid_slugs[Info_Rate]`
  and `::test_register_rejects_bad_slug_and_writes_no_event`, both in Lane 1's
  AD-028 result-name work. Untouched by this lane; green again by the end of it.
- No commits, no `seldon verify`, no graph task transitions were made here.

## 8. Test evidence

- New: `tests/test_ontology_ingest_lifecycle.py`, 25 tests.
- Changed: `tests/test_ontology.py` — `test_ingest_increments_epoch` asserted
  epoch 2 after two *identical* ingests; that test asserted the defect. It is now
  `test_ingest_increments_epoch_on_change` (identical re-ingest holds the epoch;
  a modified source advances it). `test_ingest_idempotent_no_changes` now asserts
  the no-op message.
- `tests/test_ontology.py` + `tests/test_ontology_ingest_lifecycle.py`:
  **52 passed**.
- Full suite, first run after this lane's changes: **1113 passed, 0 failed**.
- Full suite, final run: **1141 passed, 1 failed** — the failure is
  `tests/test_verify_reltype_case.py::TestCheckTaskSourceFiles::test_summary_breaks_misses_down_by_state`,
  a file another lane wrote to at 11:31 while that run was in flight. It contains
  no reference to the ontology and none of this lane's files. The suite total
  moved 1001 → 1113 → 1142 during the session because all three lanes share this
  worktree; the count is a snapshot, not a fixed baseline.
