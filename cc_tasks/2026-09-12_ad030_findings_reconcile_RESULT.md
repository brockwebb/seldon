# RESULT: AD-030 findings reconciliation, ruling patterns, dependency pin, count verification

**Date:** 2026-09-12
**Task file:** `cc_tasks/2026-09-12_ad030_findings_reconcile.md`
**Addendum read:** `cc_tasks/2026-09-12_ad030_findings_reconcile_ADDENDUM_1.md` (replaces step 7 with 7a/7b/7c)
**Seldon task:** eb359760
**Governing docs:** AD-030; AD-030 Implementation Findings 001 (rulings AD-030-R11 to R19)
**Autonomy:** L4. Nothing was escalated.

Every count below is a `{{result:NAME:value}}` reference to a **verified** Result unless it is
explicitly marked as a pre-verification figure (AD-030-R18).

---

## 1. Step 1 — ruling classification (AD-030-R16)

**Before: 171 Ruling nodes. After: {{result:governed_ruling_nodes:value}}.** 166 retired in two
passes, 10 kept, 9 added by the findings note.

The patterns in `governed/config.yaml` now classify on **position**: a ruling identifier
(`AD-NNN-Rn`, `DN-…-Rn`) or a numbered requirement ID (`FR-`, `NFR-`, `SRS-`, `SR-`, `S-`) or the
`BINDING` banner, in a heading or as the first token of a block. Anchored with `\A`, not `^`:
patterns compile with `re.MULTILINE` so heading rules can anchor, and under MULTILINE a `^` also
matches the second line of a paragraph, which is not the first token of anything.

**AD-030 now yields exactly 10 Rulings, R1 through R10.** Verified by the contract query and,
independently of the graph, by `test_exactly_ten_rulings_in_ad030_after_r16`.

### Rulings dropped, by the pattern that had matched them

| `matched_pattern` | Dropped | What it had been matching |
|---|---|---|
| `never` | 154 | the word "never" anywhere in body prose |
| `must` | 3 | "MUST" anywhere in body prose |
| `banner_binding` | 3 | "BINDING" anywhere, including where AD-030 section 4 uses it as vocabulary |
| `forbidden` | 1 | "is forbidden" in body prose |
| **Total** | **161** | |

A second pass retired five more (see G8), for 166 in all.

Full list with source document and text: `governed/work/dropped_rulings.json` (regenerable; the
retired nodes themselves carry the same information and are queryable).

Representative drops — each is ordinary narrative that the old patterns read as deontic:

- `AD-030 §1`: "Nothing was lost; nothing was bound." — `never` matched "never" in the adjacent
  sentence.
- `AD-030 §4`: "Node types: `Ruling` (a Section whose text is deontic: BINDING, MUST, never…)" —
  `banner_binding` matched the word being *defined*.
- `cc_tasks/…_RESULT.md`: "the file MUST be committed alongside its RESULT" — a note, not a ruling.

**Retired, not deleted.** A retired Ruling keeps its node and its edges: it was true of the
document once, `CONTAINS` edges point at it, and a graph that silently drops what it used to
assert cannot be audited. `governed sync` now moves absent children to `retired` on a full sync
only — a `--only` run has seen one document and knows nothing about the rest of the corpus.

## 2. Step 2 — actor gate (AD-030-R11)

**The implementation was a deny-list on `desktop`, exactly the case the step anticipated.**
`handoff.desktop_task_ids` filtered `actor != "desktop"`, and `enforce_design_reference` ran
unconditionally on the CLI regardless of actor. Both are now the allow-list of one:
`handoff.EXEMPT_ACTORS = frozenset({"cc"})` and `actor_is_gated(actor)`, used by
`seldon handoff`'s R9 gate, `seldon cc register` and `seldon_cc_register` alike. A missing actor is
gated: an event that does not say who wrote it is the case the allow-list exists to catch.

`seldon cc register` gained `--actor` (default `cc`), which is both what the gate reads and what
`created_by` records. Without it the allow-list is unimplementable on the CLI surface, because the
CLI hardcoded `actor="cc"` and would have been permanently exempt.

Tests: `test_cc_is_the_only_exempt_actor`, `test_every_other_actor_is_gated` (nine actor strings
including `CC`, `" cc"`, `"cc "`, `""` and `None` — a near-miss must not pass),
`test_an_unknown_actor_string_is_gated_at_registration`,
`test_cc_register_refuses_a_gated_actor_citing_no_decision`,
`test_cc_register_records_the_declared_actor`, and
`test_r9_gates_an_actor_that_is_neither_cc_nor_desktop` for the handoff gate.

## 3. Step 3 — dependency pin (AD-030-R17)

Pinned by **commit** in `governed/squiddy.pin`:

```
SQUIDDY_COMMIT=f23023750787ec3ca97c0a1f3b8d872445676b94
SQUIDDY_VERSION=0.2.0
```

A commit, not a version: the kit is two days old and its version moves slower than its behaviour,
and the extraction this corpus holds is a function of the parser, the assess criterion and the
acquire adapter as they stood at one commit.

`governed/check_pin.py` verifies it, and **every build target depends on it** — `catalog`, `admit`,
`plan`, `sweep`, `schema` all carry `: check-squiddy`. Pinned in a file rather than a Makefile
variable so the value is readable by the check, by a human, and by
`test_the_pin_names_a_commit` without parsing make syntax.

Failure path exercised by hand, with the pin temporarily set to zeros:

```
FATAL: the checked-out Squiddy is not the one this graph is pinned to.
  Pinned:  0000000000000000000000000000000000000000  (squiddy.pin)
  Present: f23023750787ec3ca97c0a1f3b8d872445676b94  (/Users/brock/GitHub/squiddy)
make: *** [check-squiddy] Error 1
```

`pyproject.toml` contains no Squiddy dependency; pinned by `test_pyproject_declares_no_squiddy_dependency`.

## 4. Steps 4 and 5 — the findings note, and its edges

Cataloged and admitted with the rest of the corpus. The corpus is now
{{result:governed_files_admitted:value}} governed files.

| Contract row | Measured | Verdict |
|---|---|---|
| AD-030 Rulings | 10 | PASS |
| Findings-note Rulings | 9 (R11–R19) | PASS |
| `EXTENDS` → AD-030 | `AD-028`, `AD-029`, `AD-030` | PASS |
| `DEPENDS_ON` → both RESULT Documents | both present | PASS |
| `SUPERSEDES` R17 → R10 | present | PASS |

**`SUPERSEDES` was written by hand, as the step permits, and lexical recovery of in-paragraph
supersession is a gap.** R17's text reads "Supersedes the `pyproject.toml` clause of AD-030 R10" —
a space, not a hyphen, before `R10`, inside a sentence, in the middle of a ruling paragraph. A
pattern that caught it would need to read a "Supersedes …" clause and then resolve a ruling
reference written in a form no other surface uses. That is a real recovery rule and a real risk of
false positives across 19 rulings, so it is reported rather than guessed at. The one edge was
written with `seldon link create`. R13 supersedes prose in AD-030 section 4, which is not a Ruling,
so it correctly supersedes nothing at Ruling granularity.

## 5. Step 6 — count verification (AD-030-R18)

All fourteen Results are `verified` — the thirteen from the ingest task plus
`constrained_by_edges_eb359760` registered by step 7b. Every one is re-measured from the final
post-R16 graph.

| Name | Was (proposed) | Now (verified) |
|---|---|---|
| `governed_files_admitted` | 97 | {{result:governed_files_admitted:value}} |
| `governed_document_nodes` | 97 | {{result:governed_document_nodes:value}} |
| `governed_section_nodes` | 1391 | {{result:governed_section_nodes:value}} |
| `governed_ruling_nodes` | 168 | {{result:governed_ruling_nodes:value}} |
| `governed_citation_nodes` | 37 | {{result:governed_citation_nodes:value}} |
| `governed_passage_nodes` | 389 | {{result:governed_passage_nodes:value}} |
| `governed_edges_contains` | 1948 | {{result:governed_edges_contains:value}} |
| `governed_edges_mentions` | 284 | {{result:governed_edges_mentions:value}} |
| `governed_edges_cites` | 37 | {{result:governed_edges_cites:value}} |
| `governed_edges_extends` | 7 | {{result:governed_edges_extends:value}} |
| `governed_edges_depends_on` | 9 | {{result:governed_edges_depends_on:value}} |
| `governed_edges_suspect` | 0 | {{result:governed_edges_suspect:value}} |
| `seldon_self_graph_edges_substantive` | 2298 | {{result:seldon_self_graph_edges_substantive:value}} |
| `constrained_by_edges_eb359760` | *(new)* | {{result:constrained_by_edges_eb359760:value}} |

The figures in the "Was" column are the pre-verification figures AD-030-R18 forbids quoting above
`proposed`; they appear here only as the before side of the move.

**Each governed count was made to equal what the ledger asserts.** Node counts and edge counts
exclude retired nodes, so `governed_edges_contains` is 1825 — the number of `Contains` events in
`governed/ledger/events.jsonl` — rather than 1986, which is that plus the 161 edges still pointing
at retired Rulings. A reader can now cross-check every governed count against the ledger file
without knowing anything about retirement. The AD-028 path used was value update plus
`proposed → verified`, not re-registration: a Result's *name* is its stable token key, and
re-registering under a new name to carry a corrected value is what would have broken every
reference to it.

## 6. Steps 7a and 7b — the gate, and the backfill

**7a, first attempt: zero rulings, and it was not a defect.** The addendum's fixture text is "per-set
RPE", and the ruling that forbids per-set RPE lives in Arnold's
`docs/ontology/intensity-constructs.md`, which is out of scope for this corpus. Top overlap against
the 19 binding rulings was 0.111, under the 0.18 threshold. Zero matches was the honest answer to a
question about a ruling this graph does not hold.

**7a, second attempt against a ruling this corpus does hold.** A fixture proposing "move the
governed ingest off the pre-commit hook and onto a nightly cron sweep" was registered:

```
Registered: gate fixture2 DELETEME
  id: 7e7a6afc...
Constrained by 2 ruling(s) (2 new edge(s)):
  AD-030-R19  [prohibition]  (concept overlap 0.43: able, fix, governed, ingest, uncataloged, verify)
  AD-030-R3   [binding]      (concept overlap 0.29: commit, cron, fix, governed, hook, ingest)
```

AD-030-R3 is "Ingest runs on commit, not on cron." The fixture proposed the thing the ruling
forbids, named no ruling, and the ruling surfaced anyway. That is the mechanism whose absence let
the per-set RPE field be reintroduced on 2026-09-01. Both fixtures were withdrawn with reason
"gate fixture" and their files deleted; 7c did not apply.

**7b, backfill of `eb359760`: {{result:constrained_by_edges_eb359760:value}} `CONSTRAINED_BY`
edges written.** Five by identifier — R10, R11, R16, R17, R18, each named in the task file — and
eight by concept overlap between 0.33 and 0.47: R14, R19, R1, R3, R13, R9, R6, R12. The match set
is sensible: the reconcile task genuinely touches most of AD-030, and the identifier half is exact
by construction. The concept half is capped at eight; the identifier half is never truncated.

New command, `seldon cc constrain <task|--all> [--dry-run]`. The backfill was not a one-off: 58
registered tasks predate the gate, and a task whose constraints exist only in the text of a file is
the state AD-030 exists to end.

## 7. Findings

**G1. `read_rulings` returned retired and superseded rulings.** Found by 7a's diagnosis: 180
rulings read, 19 of them binding. A retired ruling binds nothing — its text left the document — and
returning one from a match would have `cc register` constrain a new task by an obligation no
document imposes. Fixed: `NON_BINDING_RULING_STATES = {"retired", "superseded"}`, excluded by
default, with `include_non_binding=True` for auditing what was dropped. This defect could not exist
before this task, because nothing had ever been retired.

**G2. Two governed documents sharing a leading identifier collided on `name`.**
`docs/design/AD-030_governed_documents_as_graph_content.md` and
`docs/design/AD-030_implementation_findings_001.md` both derived the name `AD-030`, so the contract
query returned 19 rulings from two documents and `EXTENDS` returned the union of both documents'
edges. Fixed: the bare identifier goes to the first claimant in **sorted path order** and every
later one keeps its full stem, which is deterministic and stable across runs. Assignment runs over
every document in the ledger, not over the subset being synced, so a `--only` run cannot hand out a
name a full run would give to someone else. **The deeper issue is that a governed document cannot
declare its own canonical name**; sorted-path-first-claim is a tiebreak, not a statement of intent,
and it happens to give `AD-030` to the decision document only because `governed` sorts before
`implementation`. A `Name:` header field would settle it properly. Reported, not fixed: adding a
header field is an AD-030 change and AD-030 is not edited here.

**G3. The content hash does not cover a derived property, so a derivation change could not reach
the graph.** `sync` skipped a document whose hash matched, which is right for content and wrong for
`name`: after fixing G2 the mis-named node would have kept its name forever. Fixed: a document is
re-written when its hash moved **or** its computed name differs from the stored one.

**G4. A name-only update flagged 123 edges suspect.** `changed_documents` was appended on every
update rather than on a content-hash change, so re-deriving a name asked for review of links
nothing had disturbed. A suspect flag that fires on non-events is one people learn to clear without
reading. Fixed: suspect follows the content hash. The 24 residual flags from the run that exposed
this were cleared.

**G5. Header-field edges resolved identifiers only, never paths.** The findings note's
`Depends on:` names two RESULT files by repo-relative path, so both `DEPENDS_ON` edges were
dropped in silence. Fixed: `document_index` returns a path index alongside the identifier index and
`emit_layer` resolves both, with each target yielding at most one edge. Without this, step 5's
contract row could not have been met by the recipe at all.

**G6. Lexical recovery of in-paragraph supersession is a gap.** See section 4. One edge written by
hand; the pattern is not attempted.

**G9. An edited governed document has no incremental re-ingest path.** `squiddy.assess` stops at
`already_admitted` on any document whose id is already in the ledger, without consulting the
content hash, so `make -C governed admit ID=<changed doc>` decides-and-stops and never re-extracts.
The only route today is `governed/reset.sh` plus a full sweep — about six minutes for 102 files,
and it rewrites the whole ledger to pick up one edited paragraph. This task hit it four times,
including on its own RESULT file: editing this document after admission moved its hash, and
`seldon verify` correctly failed on it. Seldon's half is already incremental —
`governed sync` is idempotent by hash and touches only what moved — so the gap is entirely on the
extraction side. The fix is a kit change: `assess` should compare the manifest's recorded sha256
against the file and treat `admitted but changed` as admissible, with the write stage's existing
`--resume` semantics appending updated node events that `latest_by_key` merges last-write-wins.
Not attempted here: it is a Squiddy change with ledger-semantics consequences, and no step of this
task asks for it. Reported so the next governed-documents task starts from it.

**G8. Position alone was not enough: a document that DISCUSSES rulings wrote five of its own.**
The first R16 patterns admitted `## 2. Step 2 — actor gate (AD-030-R11)` and
`AD-030-R3 is "Ingest runs on commit, not on cron."` — a section heading citing a ruling, and a
sentence about one. Both are first-token or heading position, so position satisfied them; neither
states a ruling. Found by this task's own RESULT file producing five Rulings on its first
admission. The patterns now require the identifier to be used as a **label**: terminated by `.` or
`:`, or bolded, and opening the heading text rather than appearing anywhere in the first forty
characters of it. AD-030 yields 10, the findings note 9, and every RESULT and task file in the
corpus yields 0 — which is right, because a RESULT reports on rulings and does not make them.
This is the same class of error R16 was written to fix, one level in: R16 moved classification
from vocabulary to position, and position turned out to need the label/mention distinction on top.

**G7. `force` would have collapsed to a single value under a literal reading of R16.** R16 governs
*classification*. If the same positional patterns also supplied force, every Ruling would be
`binding` and the axis that separates a prohibition from a recommendation would be gone. Force is
now read from the ruling's own text by a separate `force_patterns` list, run only over blocks
already admitted as rulings. R16 says deontic words in body prose must not *classify*; it does not
say the force of text that is already a ruling may not be read. Recorded because it is a reading of
R16, not a quotation of it.

## 8. Step 8 — suite and verify

- Seldon suite: **1682 passed** (1645 before this task's tests, 1628 at the start of the session).
- `seldon verify --strict`: exit 0, all 13 checks, **zero uncataloged governed files**.
- The corpus was swept four times: `r16_20260912` (first R16 patterns), `result_20260912`
  (this RESULT file), `r16b_20260912` (the G8 tightening, full re-extraction) and
  `final_20260912` (this document as finally written — see G9 for why a full sweep is the only
  way to re-ingest one edited file). The Results in section 5 are measured against the last.
- Squiddy: no Squiddy file changed by this task; its suite is unchanged at 107 passed and its
  pinned commit `f230237` is the one this graph builds against.

## 9. Scope boundaries observed

- `AD-030_governed_documents_as_graph_content.md` and `AD-030_implementation_findings_001.md` not
  edited. Every finding is in this file.
- DI-005 not relaxed. No Neo4j projection into any `seldon-*` database from Squiddy.
- Zero model calls.
- Arnold corpus untouched.
- `seldon handoff` and `seldon closeout` remain distinct; no second closeout term introduced.
