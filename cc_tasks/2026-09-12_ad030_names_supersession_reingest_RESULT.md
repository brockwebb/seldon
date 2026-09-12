# RESULT: AD-030 names, supersession syntax, incremental re-ingest, constraint backfill

**Name:** AD-030-T-NAMES-RESULT
**Date:** 2026-09-12
**Task file:** `cc_tasks/2026-09-12_ad030_names_supersession_reingest.md`
**Addendum read:** `cc_tasks/2026-09-12_ad030_names_supersession_reingest_ADDENDUM_1.md` (amends steps 5 and 6)
**Seldon task:** 85b26c9e
**Governing docs:** AD-030; AD-030 Implementation Findings 001 (AD-030-R11 to R19); AD-030 Implementation Findings 002 (AD-030-R20 to R24)
**Kit:** squiddy 0.3.3, commit `5611cf4`, merged to main and pushed before each pin move
**Autonomy:** L4. Nothing was escalated.

Every count below is a `{{result:NAME:value}}` reference to a Result in the graph. Figures written
as literals are the ones AD-030-R18 does not cover — process facts about this run rather than
measurements of the corpus — and are marked where they appear.

---

## 1. Step 1 — incremental re-ingest, Squiddy side (AD-030-R22)

**Kit 0.3.0.** An admitted entry was waved through on identity alone: `assess` answered
`already_admitted` whenever the id was in the ledger and never asked whether the bytes it named
still hashed to what the manifest recorded. That is the right question for an immutable corpus and
the wrong one for a repository pointed at its own governed files, where the only way to pick up one
edited paragraph was to wipe the ledger and re-sweep.

Five changes, all generic, none of them aware of Seldon (AD-030-R10):

**`assess.content_moved`** hashes the file the entry names and compares it against the manifest's
recorded `sha256`. A disagreement is decision `admit` with reason code `content_changed`, and both
hashes are in the reason. An entry that records no hash, or names a file that is not there, is
abstained on: there is nothing to compare, and an unanswerable question is not a change.

**`write.read_stage`** takes the re-ingest path without a flag. By the time it runs, acquire has
already written the new hash into the manifest, so the manifest and the ledger disagree exactly
when the document has been re-read since it was last written; `--reingest` is kept for a
re-extraction the hash cannot see, such as a changed emitter. `scope` gained one rule for that
path: a node whose payload has not moved is dropped as unchanged, so the ledger grows by the edit
and not by the document.

**`write.retractions`** retracts the children the new extraction no longer has. Retire, not delete:
the retraction is an event, the ledger keeps the whole history, and only the projection stops
carrying the node — which is what makes Seldon's `retire_absent_children` fire on an edit without a
reset. It is scoped twice over. By document, because a node another document also asserts is not
this one's to retract. And by the stage that wrote it, because the read stage owns what it
extracted and a layer owns the cross-document edges it added, and neither may retract the other's
work.

**`project.build_graph` folds retractions in ledger order.** The replay collected every retraction
and applied it after every assertion, which was indistinguishable from correct while a retraction
only ever ended something. The moment a child can be retracted by one re-ingest and asserted again
by the next, the earlier retraction wins forever and the child is invisible. `latest_by_key` had
always merged in order; the two now agree.

**`canary.predict` counts a retraction as -1.** Without it, a re-ingest that drops a ruling shows a
measured -1 against an expected 0, and the gate that exists to catch undeclared changes reports the
declared one as a mismatch.

One further change the pipeline forced. `squiddy admit --layer <name>` runs admit to check-after,
then the layer, then the release. A layer appended after the export leaves the served copy behind by
exactly those edges, and the next admission's check-before reports drift — so the order is not a
preference.

**Tests: 29 new, 136 passing** (literal; the kit's suite, not a corpus measurement). They pin the
four behaviours step 1 names — an edited document re-extracts alone, an unchanged one is skipped, a
removed child is retracted rather than deleted, an unrelated document's events are untouched —
plus the two replay rules that make them true.

## 2. Step 2 — incremental re-ingest, governed side

**A full sweep of this corpus takes
{{result:governed_reingest_full_seconds:value}} {{result:governed_reingest_full_seconds:units}};
re-ingesting one edited document takes
{{result:governed_reingest_single_seconds:value}} {{result:governed_reingest_single_seconds:units}}.**
Both measured on the same machine with the same kit and the same per-admission gate set, so they
are comparable: the sweep figure is 105 admissions, 105 layer runs and one release; the single
figure is this document, edited after admission and re-admitted through
`make -C governed admit ID=<doc_id>`, with its edge layer and its release.

Most of the single figure is not the re-ingest. The read stage's own work is 0.54 seconds — 33
events built, 5 appended, the rest dropped as unchanged or already in the ledger. The rest is the
per-admission gate set, of which 8.4 seconds is the kit's own test suite (see F4).

The two are not the same operation at different sizes. The sweep rewrites the ledger; the re-ingest
appends one document's delta and leaves every other document's events byte-for-byte as they were.

`governed/reset.sh` stays as the reset path and its header now says so, naming the case it is for —
a recipe change, where every document's extraction really has moved — and naming `make admit` as
the edit path.

`make -C governed admit ID=<doc_id>` now passes `--layer references`, and the Makefile names the
layer in a variable rather than leaving it to be remembered on the command line. The kit's default
layer name is `cites`; this graph declares `references`; a sweep that forgets to say so runs a
layer over nothing and reports success.

## 3. Step 3 — the `Name:` header field (AD-030-R20)

**The recipe reads `Name:` from the header block** — the same block `Extends:` and `Depends on:`
are read from, so a `Name:` below the first rule or the first `##` heading is prose. The value
lands on the Document node as `declared_name`, deliberately outside `manifest_projection`: the
drift gate compares exactly those fields against the manifest, and this one is read from the
document's text, which the manifest never holds.

**Seldon's importer treats a declaration as authoritative.** `assign_names` claims declared names
first, in one pass, and the filename derivation then works around what is left. A consequence worth
stating: adding the field to one document can take a name away from another that held it only by
the sorted-path tiebreak. That is the correct direction — the tiebreak was never a statement of
intent.

**Nothing was backfilled.** Existing documents keep their derived names.
`seldon governed status` now reports the documents whose derived name lost the tiebreak, naming
what each wanted and what it holds, so the operator can settle it with a header field. There are
four: the three `AD-020_*` design notes, and `AD-030_implementation_findings_001.md`, which wanted
`AD-030` and holds `AD-030_implementation_findings_001` because `governed` sorts before
`implementation`. None of them is broken — the assignment is deterministic and stable — but each
holds a name nobody would guess, and that is now visible rather than latent.

This document declares `Name: AD-030-T-NAMES-RESULT`, so the mechanism is exercised on itself.

Contract query: the Document for `AD-030_implementation_findings_002.md` has `name` **AD-030-F002**
and `declared_name` **AD-030-F002**.

## 4. Step 4 — supersession (AD-030-R21)

Two patterns, both declarations, nothing inferred.

**Ruling level.** One configured pattern over the text of a block already admitted as a Ruling:
`Supersedes` followed by one or more hyphenated ruling IDs, ending the sentence. The edge is
emitted by the cross-document layer rather than at admission, because the ruling being superseded
may not be in the ledger yet. Targets are resolved against the ledger's own ruling ids and the
recovery abstains when an identifier resolves to none or to more than one.

**Document level.** A `Supersedes:` header field, resolved by identifier or by repo-relative path
through the mechanism `Extends:` already used.

**The hand-written R17 to R10 edge was removed, the corpus was re-swept, and the recipe did not
re-create it. That is the expected and correct outcome.** AD-030-R17 writes "Supersedes the
`pyproject.toml` clause of AD-030 R10." — prose *about* a supersession, with a noun phrase after
the verb and an unhyphenated reference. It is not the declared form, and a pattern loose enough to
catch it would read every sentence containing the word. The edge was re-created by hand, carrying
that explanation as its `reason`, and it remains the one hand-written `SUPERSEDES` edge in the
graph.

Across the whole corpus, no ruling text and no header field matches either pattern today. The
recovery is in place for the rulings that will declare it; R21 governs how they must write it.

## 5. Step 5 — R16 readings, and the gate defect (AD-030-R23, R24, addendum 5a-5c)

### 5.0 The readings shipped in the reconcile task match the ruling text

`force_patterns` runs only over blocks already admitted as rulings and reads force from the
ruling's own text — R23's first clause. The label-versus-mention rule is R23's second. Tests were
added per clause: an identifier used as a label classifies in each of its five written forms; an
identifier merely mentioned does not, including the two real cases G8 found; force is read
separately and produces four different values over four rulings with identical position; and a
deontic word in body prose still classifies nothing. `read_rulings` excludes `retired` and
`superseded` by default, and a superseded ruling is refused the same way a retired one is.

### 5.1 (5a) Why the gate matched retired rulings

**The query had the filter; the process did not.** The nine bad edges on `85b26c9e` were written by
an MCP server process holding `seldon.core.governed` as it stood *before* `NON_BINDING_RULING_STATES`
shipped. Established by elimination, on the record and not by inference: the reconcile merge landed
at 16:31 UTC, the retirements at 16:20 UTC, and the edges at 20:11 UTC — after both. Running the
same task file through the same function on disk today returns nine rulings, all `admitted`. The
CLI path and `seldon cc constrain` were checked and were never affected.

The retired rulings scored 0.75, 0.751 and 0.5 against this task's text, which is why they did not
merely appear alongside the real matches but **crowded them out**: the concept half of a match is
capped at eight, and nine retired rulings filled it.

Three things follow, and only the first is the fix for the defect as reported:

1. **`match_rulings` filters too, and it is pure.** A guard that lives only in a Cypher `WHERE`
   clause protects the query, not the decision. The matcher now drops any ruling carrying a
   non-binding state whatever fetched it, which is testable without a database.
2. **`write_constrained_by` reads the state live and refuses.** This is the guard that would
   actually have caught the stale process, because it runs at the moment of the write with the
   graph in front of it. It returns what it refused, and `constraining_rulings` drops those from
   the matches it reports, so what is shown is what was written.
3. **`seldon verify` gained a Tier A check, `Binding constraints`.** A guard nothing checks goes
   stale. The check is zero in a clean graph, names the task and the ruling when it is not, and
   `--fix` removes the edges through `remove_link` so the repair is itself an event.

### 5.2 (5b) The nine edges, and the gate re-run

`seldon verify --fix` removed all nine, each named in the output. Re-running the gate over the task
file then wrote **13 rulings, every one `admitted`**: five by identifier (AD-030-R10, R20, R21, R22,
R23 — each named in the task file) and eight by concept overlap between 0.31 and 0.75. The highest
concept match is `Addendum 029-A` at 0.75, which is 5c's ruling binding a task on the first day it
exists.

### 5.3 (5c) The ruling R16 lost

`# Addendum 029-A: Seldon never reads a relationship by name alone` had been admitted by the word
`never` in its own text, so retiring the `never` pattern retired a real ruling with it. It is a
ruling ID opening a heading and terminated by `:`, which is what AD-030-R23 calls a label. Added to
the pattern list as `addendum_heading`, with the colon required for the same reason it is required
of a ruling identifier — `## What Addendum 029-A changed` is a heading about one.

**Ruling count delta: +1 admitted, and no cc_task or RESULT file gained a ruling from the change.**
Across the corpus exactly one heading matches the new pattern. Every RESULT and task file still
yields zero rulings, which is the check that matters: this pattern set has been tuned twice now,
and both times the failure mode was a document that *discusses* rulings writing its own.

**The recovered ruling came back under a new id, and the old one stayed retired.** `!r002` was an
ordinal key — the third unidentified ruling in AD-029 — and under the tightened patterns the other
four are no longer rulings at all, so `!r002` no longer names anything. The heading now carries the
identifier `Addendum 029-A` and the key `!addendum_029_a`, which is stable under every edit to its
neighbours. See finding F3: this is a property of ordinal keys, not of this document.

## 6. Step 6 — constraint backfill

Dry run reviewed before the live run, as the addendum requires:

| | |
|---|---|
| Registered tasks whose source file is on disk | 20 |
| Tasks matching no ruling | 0 |
| Proposed edges | 137 — 13 by identifier, 124 by concept overlap |
| Edges per task | 1 to 13; median 8 |
| Tasks matched by more than eight concept rulings | 0 (the concept half is capped at eight) |
| Proposed edges whose target is not `admitted` | **0** |

The 20 is the honest ceiling, not a subset: 59 registered tasks carry a `source_file` and 39 of
those files are gone — finished tasks whose spec was not kept. A task with no text has nothing to
match against, which is a fact about the file rather than a failure here.

Live: **{{result:tasks_constrained_backfill:value}} tasks,
{{result:constrained_by_edges_backfill_total:value}} new `constrained_by` edges.** The graph now
holds {{result:constrained_by_edges_total:value}} such edges across
{{result:tasks_constrained_total:value}} tasks, none of them pointing at a ruling that no longer
binds.

## 7. Step 7 — catalog, admit, and the counts re-verified under R18

Findings 002, this task file, its addendum and this RESULT were cataloged; the corpus went from 102
governed files to {{result:governed_files_admitted:value}}.

**The corpus was swept in full rather than re-ingested document by document, and R22 is why.** The
recipe moved in this change — a new header field, a new ruling pattern, a new supersession pattern
— so every document's extraction moved with it, whatever its bytes did. That is precisely the case
R22 leaves to the reset path. This RESULT was then admitted and re-admitted through the
single-document path, which is what section 2 measures.

Counts after the sweep and the sync, every one re-derived and re-verified:

| Result | Value |
|---|---|
| `governed_document_nodes` | {{result:governed_document_nodes:value}} |
| `governed_section_nodes` | {{result:governed_section_nodes:value}} |
| `governed_ruling_nodes` | {{result:governed_ruling_nodes:value}} |
| `governed_citation_nodes` | {{result:governed_citation_nodes:value}} |
| `governed_passage_nodes` | {{result:governed_passage_nodes:value}} |
| `governed_edges_contains` | {{result:governed_edges_contains:value}} |
| `governed_edges_mentions` | {{result:governed_edges_mentions:value}} |
| `governed_edges_cites` | {{result:governed_edges_cites:value}} |
| `governed_edges_depends_on` | {{result:governed_edges_depends_on:value}} |
| `governed_edges_extends` | {{result:governed_edges_extends:value}} |
| `governed_edges_supersedes` | {{result:governed_edges_supersedes:value}} |
| `governed_edges_suspect` | {{result:governed_edges_suspect:value}} |
| `governed_rulings_retired` | {{result:governed_rulings_retired:value}} |

`governed_ruling_nodes` counts rulings that bind. Retired rulings keep their nodes and their edges
(AD-030-R24) and are counted separately.

Rulings by document, which is the contract's own check:
**AD-030 10, Findings 001 9, Findings 002 5, AD-029 1, every RESULT and task file 0.**

## 8. Findings

**F1. A content hash covers the file, and the children come from the recipe.** The first sync after
the sweep reported 102 of 105 documents unchanged and created nothing for them — correct by the
test it was applying, and wrong. `unchanged` compared the file hash and the derived name, both of
which are properties of the *document*; the sections, rulings, citations and passages are
properties of the *extraction*, and a new ruling pattern moves them with the file untouched. The
Addendum 029-A ruling was invisible to the graph for exactly one sync because of it. Fixed: the
Document carries a `children_fingerprint` — a digest over its children's ids and content hashes as
the ledger holds them — and `unchanged` requires all three to match. The second sync created the
missing ruling; the third reported 105 unchanged, so the test is idempotent. This is the same class
of defect as G3 in the reconcile RESULT, one level further out: G3 found that a derived *name*
could not reach the graph, and this is the derived *children*.

**F2. `retired` is terminal, so a child whose id returns is reported and not revived.**
`research.yaml` declares no transition out of `retired` for a Section, Ruling or Passage, and that
is deliberate — the span left the document and the graph recorded a deletion. A ledger that holds
the id again is a real event, and the sync now reports it rather than quietly updating a retired
node back into service, which would make the retirement a lie in retrospect. Zero occurrences in
this run; the reporting exists because the next ordinal-keyed reshuffle will produce one.

**F3. Ordinal ruling keys are not stable, and the fix is to give the ruling a label.** A ruling
with no identifier is keyed `!rNNN` by its position among the *other* rulings of its document, so a
pattern change elsewhere in the same file silently reassigns the key. In AD-029 the Addendum
heading was `!r002` under the old patterns and would have been `!r000` under the new ones — the
same key one of its neighbours used to hold. Nothing in this corpus was corrupted by it, because
`Addendum 029-A` is now recognised as an identifier and the ruling is keyed by that. Reported, not
generalised: making every unlabelled ruling content-keyed would mint a new node on every edit of
its text, which trades one churn for another. The rule this supports is the one AD-030-R20 already
states for documents — a thing that wants a stable identity should declare one.

**F4. The kit's fast test tier runs once per admission, and it is most of a sweep.** Each of the
105 admissions spends about 8.4 seconds of its 10.3 on the kit's own 127 tests, because the stage
record that gates it is written per admission version. It is not wrong — nothing writes to a ledger
in this kit without its unit tests passing first — but it means a corpus sweep scales with the kit's
suite rather than with the corpus, and it is the largest single reason the reset path is expensive.
Reported against the kit, not fixed here: the fix is a decision about where that gate belongs, and
this task has no step for it.

**F5. The emitter was edited while the sweep that used it was running.** A caching helper in
`governed/emit.py` — the process-level cache for declared names — was changed in the middle of the
105-document sweep, and because the kit loads the emitter by file path for every call, the later
admissions ran the newer file. The change is a memoisation and cannot alter what is extracted, and
every stage gate, the canary and the drift legs passed on every admission. It is recorded because
"it cannot have mattered" is exactly the claim a reproducibility pin exists to stop anyone making
about a build: the correct sequence is to finish the run, then change the recipe, then re-run.

**F6. The kit is not on the default interpreter, and the Makefile did not say so.** Every
`make -C governed` target needs `PY=` pointing at an interpreter that has Squiddy, because
AD-030-R17 keeps the kit out of `pyproject.toml` and the default `python` therefore does not have
it. The failure is loud — `check-squiddy` names it — but it was an unwritten incantation. Named in
the Makefile header now.

**F10. Cross-document `mentions` edges stay suspect after a re-derivation, and that is right.**
`clear_suspect` runs over the child artifacts the sync re-derived, so a Document's own `mentions`
edges are left flagged when its hash moves. They are the edges most worth a human eye — an
identifier this document names in another one — and clearing them automatically would make the
flag mean "re-derived" rather than "reviewed". The three raised by this document's last edit were
read, still hold, and were cleared deliberately.

**F7. A `--only` sync cannot retire, and after a single-document re-ingest that is visible.**
`retire_absent_children` runs only on a full sync, because a `--only` run has seen one document and
knows nothing about the rest of the corpus. The incremental path therefore ends in a full
`seldon governed sync`, which is cheap — it is idempotent by the three-part test above and touches
only what moved. Not a defect; recorded because "re-ingest one document" on the Squiddy side does
not mean "sync one document" on the Seldon side.

**F8. The first real re-ingest failed three times, and each failure was a different thing that had
only ever been asked one question.** Reported as one finding because they are one story: a stage
that had only ever run once per document, run twice.

1. **The evidence directory was keyed by the day.** The pipeline is a make DAG whose targets are
   stage records under `evidence/<label>`, and the label was date-plus-id. A second admission of
   one document on one day found every record already on disk, skipped all thirteen stages and
   failed at the export, which correctly refuses to overwrite a versioned artifact. It reported
   thirteen stages passed and had re-extracted nothing. Fixed in kit 0.3.1: the label carries the
   first eight characters of the file's hash, so a re-run of the same content resumes and a
   re-admission of changed content runs.

2. **The parse cache was keyed by the document id.** Worse, because this one ran. With a fresh
   label every stage re-ran, and the parse stage returned its cached intermediate — made from the
   *previous* version of the file — because it never asked whether the bytes had moved. The write
   stage then appended a Document node carrying the new hash and sections carrying the old text,
   and **every gate passed**: the manifest and the ledger agreed about the hash, the canary counts
   nodes rather than reading them, and nothing downstream compares the text. Fixed in kit 0.3.2:
   the intermediate carries `source_sha256`, the cache is invalidated against it, and the stage
   asserts what it produced rather than trusting that the invalidation worked.

3. **`--reingest` never reached the stage that decides.** The flag forced the write stage. Assess
   runs first, answers `already_admitted` for a document whose bytes have not moved, and that is a
   decision stop — so the pipeline halted and the write stage was never run, in exactly the case
   the flag exists for. Fixed in kit 0.3.3.

The second is the one worth keeping. A silent staleness inside a document is invisible to every
gate this kit has, because all of them compare *counts* and *hashes of the file* and none of them
compares the *text that was extracted from it*. The check that catches it has to live at the parse
stage, which is the only place that knows both what it read and what it was supposed to read.

**F9. A forced re-ingest over unchanged content collides with its own export, loudly.** With the
label content-addressed, `--reingest` on a document whose bytes have not moved reuses the label by
construction and the export refuses to overwrite the artifact of the previous run. The failure is
loud and names the remedy — `--version <label>` — which is the kit's designed escape hatch rather
than a workaround. Left as it is: making the label auto-unique under `--reingest` would trade a
loud stop for a silently growing set of near-identical releases, and this path is for a recipe
change, which is a deliberate act.

## 9. Step 8 — suites and verify

- **Squiddy: 136 passed** (107 before this task; 29 new in `tests/test_reingest.py`, across kit
  releases 0.3.0 to 0.3.3).
- **Seldon: 1714 passed** (1682 before this task; 32 new across `tests/test_governed.py`, plus the
  check-count wiring test in `tests/test_verify_event_log.py` moved from 13 to 14).
- `seldon verify --strict`: exit 0, **all 14 checks**, zero uncataloged governed files, zero
  `constrained_by` edges to a ruling that no longer binds.

The order of the last few steps is worth recording because it is the loop AD-030-R22 was written to
make possible, run for the first time on its own RESULT. This file was written, cataloged, admitted,
then edited, then re-admitted through `make -C governed admit`, which re-extracted one document and
left the other 105 alone. Before R22 the same edit cost a reset and a full sweep, and the reconcile
task paid that four times, once on its own RESULT. It also took three kit releases to make the loop
actually work, which is F8 and is the most useful thing this task produced.

## 10. Scope boundaries observed

- AD-030, Findings 001 and Findings 002 were not edited. Every finding above is in this file.
- DI-005 not relaxed. Squiddy still projects to no `seldon-*` database.
- Zero model calls.
- Arnold corpus untouched. It remains blocked on nothing now that R22 has landed, and is the next
  task's business rather than this one's.
- `seldon handoff` and `seldon closeout` remain distinct; no second closeout term introduced.
