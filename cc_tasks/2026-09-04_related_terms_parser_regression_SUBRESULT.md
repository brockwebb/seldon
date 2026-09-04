# SUBRESULT — `_parse_related_terms` section-boundary regression (Lane 4)

**Date:** 2026-09-04
**Worktree:** `/Users/brock/GitHub/seldon/.claude/worktrees/defect-fixes-ad028`
**Scope:** `seldon/ontology/parser.py`, `tests/test_ontology.py`,
`tests/test_ontology_ingest_lifecycle.py`, new `tests/test_parser_sections.py`,
plus one live repair of the shared `seldon-ontology` master and a sync of
`seldon-seldon-self`.

---

## 1. Root cause — confirmed in substance, corrected on the evidence

The defect is exactly as described: `_parse_related_terms` expected a pipe table,
the section is a definition list, and the parser's unbounded forward scan ran
past the section and parsed the *next* table in the file.

**Two corrections to the brief.**

### 1a. The commit is `b6714f3`, not `62d6bdf`

`62d6bdf` (2026-04-17, "feat(glossary): centralize enforcement") did not change
the Related Terms section from a table to a definition list. That section was
*already* a definition list in `62d6bdf^`. The conversion happened three weeks
earlier in **`b6714f3` (2026-03-28), "Ontology: context buffer → context window
terminology update (AD-017)"** — a 29-insert/9-delete edit to
`VALIDITY_VOCABULARY.md` only.

Evidence:

```
$ git show a379481:ontology/validity/VALIDITY_VOCABULARY.md | grep -A 8 '^## Related Terms'
## Related Terms (Defined Elsewhere)

| Term | Brief Meaning | Canonical Source |
|------|---------------|-----------------|
| Context window | The token buffer containing the system's current operative state ... |
| Compaction | Automated summarization/truncation of context to fit window limits | ... |
...

$ git show b6714f3:ontology/validity/VALIDITY_VOCABULARY.md | grep -A 8 '^## Related Terms'
## Related Terms (Defined Elsewhere)

**Context window**
: The mutable content that accumulates during pipeline operation — the literal
  instrument in LLM pipelines (combined with fixed model weights). ...
```

`a379481` (2026-03-22) created the file with the table; `b6714f3` (2026-03-28)
replaced it with the definition list. `62d6bdf` only moved `Token limit` out of
Related Terms into the new `## Core Instrument Terms` section.

So the mis-parse was live for **five months and one week** (2026-03-28 →
2026-09-04), not four months, and the commit to cite in any incident record is
`b6714f3`.

### 1b. The failing line

`seldon/ontology/parser.py`, in `_parse_related_terms` before this change:

```python
for i, line in enumerate(lines):
    if line.strip().lower() == "## related terms (defined elsewhere)":
        j = i + 1
        while j < len(lines) and not lines[j].strip().startswith("|"):
            j += 1                      # <-- no stop condition
        rows, _ = _parse_table_rows(lines, j)
```

The `while` loop's only bound is the end of the file. With the section's own
table gone, `j` advanced 20 lines past the section end and landed on the
`## Terms That May Be Promoted from Projects` table. `_parse_table_rows` then
read that table's columns positionally — `row[0]` Candidate Term, `row[1]` Origin
Project, `row[2]` Status — and `row[1]` was assigned to `definition`. Hence two
terms whose entire definition is the string `leibniz-pi`.

The identical unbounded-scan idiom was present in six other parsers
(`_parse_sub_dimensions`, `_parse_threats`, `_parse_severity`, `_parse_tax_tiers`,
`_parse_countermeasures`, `_parse_metrics`, plus the rejected-terms table inside
`_parse_terminology_decisions`). None had leaked yet, purely because their
sections still contained tables.

### 1c. Why no test caught it

`tests/test_ontology.py::TestParser` asserted counts and IDs for every category
**except `related_term`** — the word "related" did not appear in the file. The
category with no assertion is the category that broke.

---

## 2. The fix

### 2a. Bounded section scanning

New helpers in `seldon/ontology/parser.py`:

| Helper | Role |
|--------|------|
| `_heading_level(line)` | ATX heading depth, `0` for non-headings |
| `_find_section(lines, heading, prefix=False)` | Resolves a heading to `(start, end)`, where `end` is the next heading at the same or a shallower level. Exact case-insensitive match by default; `prefix=True` tolerates a trailing parenthetical |
| `_section_table_rows(lines, heading)` | The first pipe table **inside** that range, empty list otherwise |
| `_parse_definition_list(lines, start, end)` | `**Term**` / `: body` pairs within a range |
| `VocabularyParseError(ValueError)` | Loud failure type; subclasses `ValueError` so existing `except ValueError` callers are unaffected |

Every section parser now resolves its bounds first and scans only inside them.
Cross-section leakage is structurally impossible, not merely unlikely.

`_find_section` matches headings **exactly** by default. This matters here:
`## Framework Terms` and `## Framework Terms (Cross-Cutting)` are two different
sections, and a prefix match would have merged them.

### 2b. `_parse_related_terms` — definition-list only, deliberately

Rewritten to read the definition list. First `:` line becomes `definition`;
subsequent `:` lines (usage guidance, "do not write" notes) go to
`extra["usage_note"]`. The old `extra["canonical_source"]` key is dropped — it
was a table column that no longer exists. `extra` is persisted as opaque JSON
(`seldon/commands/ontology.py:239`), so no consumer depends on the key name.

**Decision: do NOT retain the table branch.** Reasons, in order of weight:

1. **Supporting both is the bug.** A parser that accepts "whatever shape turns up
   next" is precisely what walked into the wrong section. Narrowing the accepted
   shape is part of the fix, not a cost of it.
2. **No live vocabulary uses tables for term definitions.**
   `ontology/practitioner/PRACTITIONER_VOCABULARY.md` — checked as instructed —
   contains **zero** lines beginning with `|`, and is parsed by a separate
   definition-list parser (`seldon/ontology/practitioner_parser.py`). The
   validity vocabulary has moved the same direction: `62d6bdf` added two more
   definition-list sections. The table form exists only at `a379481` in history.
3. **Dead code is a standing liability** (repo standards §1, §8).
4. **A revert is caught, not absorbed.** If the section ever went back to a
   table, `_parse_related_terms` would return `[]` and the new runtime guard
   would raise, naming the section and the parser. That is a better outcome than
   silently parsing it.

Test `test_practitioner_vocabulary_has_no_tables` pins premise (2), so the
decision fails a test rather than rotting if the premise changes.

---

## 3. Making the *class* of bug detectable

The requirement was that a future regression of this shape fails a test rather
than mis-parsing silently. Three mechanisms, at three different strengths:

### 3a. Structural (cannot be violated)

Bounded scanning, above. A parser cannot see another section's content.

### 3b. Runtime, ships to every project — `parse_vocabulary` raises

`SECTION_COVERAGE` declares, for every `##`/`###` heading in
`VALIDITY_VOCABULARY.md`, which parser claims it and how many terms it yields.
`_check_section_yields` raises `VocabularyParseError` if a claimed section is
**missing** or **yields zero terms**, naming the heading and the parser:

```
Vocabulary parse incomplete for .../VALIDITY_VOCABULARY.md:
  - section '## Related Terms (Defined Elsewhere)' yielded no terms of category
    'related_term' via _parse_related_terms(), but the section is present. Its
    content no longer matches the shape _parse_related_terms() parses
```

This is the assertion that would have fired on 2026-03-28.

**The runtime floor is one term, not N — deliberately.** Deleting one row from a
table is a legitimate vocabulary edit. Failing every downstream project's ingest
over it would be a worse failure than the one being prevented. This replaced the
previous `_EXPECTED_MINIMUMS` block, which covered only five categories and not
`related_term`.

### 3c. Repo CI, against the real file — exact counts and exact headings

`tests/test_parser_sections.py::TestSectionCoverage` enforces what the runtime
deliberately does not:

- `test_every_heading_is_declared` — every `##`/`###` in the file appears in
  `SECTION_COVERAGE`. A new section forces an explicit decision.
- `test_no_stale_declarations` — no declaration for a section that is gone.
- `test_headings_are_unique` — duplicates would make bounded lookup ambiguous.
- `test_declared_counts_match_actual_counts` — per-section exact counts.
- `test_total_term_count` — total equals the sum of declarations, catching terms
  arriving from a section that declares none (the direct leak signature).

Splitting strictness this way keeps the strict check where a failure is
reviewable (CI, one-line fix) and the lenient check where a failure is
destructive (a user's ingest).

---

## 4. Tests

`tests/test_parser_sections.py` (new, 19 tests), all against the **real**
vocabulary file — the regression was invisible to synthetic fixtures because a
hand-written fixture reproduces the shape the parser already expects. Boundary
fixtures are built by *mutating* the real file, not inventing one.

- `TestRelatedTermsRegression` — all five terms parse with their real definition
  text (fragment-matched, not just counted); the two junk IDs are absent; **no**
  term anywhere has `leibniz-pi` as its definition (asserts the *signature*, so a
  different column leaking the same way is also caught); usage notes stay out of
  definitions.
- `TestSectionBounds` — heading-level parsing; section end at the next
  same-or-shallower heading; exact match does not collide with
  `## Framework Terms (Cross-Cutting)`; **`test_reformatted_section_does_not_steal_the_next_table`**
  reproduces the exact b6714f3 shape (gut the section, keep the next table) and
  asserts an empty parse; emptied and renamed sections raise
  `VocabularyParseError`; a single-row deletion does *not* break ingest.
- `TestSectionCoverage` — as in §3c.

`tests/test_ontology.py::TestParser::test_parse_related_terms` added — the
missing assertion that would have caught this, in the class where its absence
was the hole.

`tests/test_ontology_ingest_lifecycle.py` — Lane 2's orphan fixture used
`| Log-precision fitness` (a junk row) as its removable term. That row is no
longer a term, so the fixture removed nothing and eight tests failed. Repointed
to the real `**Fidelity**` entry in Related Terms, with an assertion that the
block is still verbatim in the file so the fixture cannot silently rot the same
way.

### Suite state

```
$ python -m dotenv -f .env run -- python -m pytest tests/ -q
2 failed, 1176 passed in 69.75s
```

Both failures are **Lane 3's**, not this lane's:

- `tests/test_mcp_tools.py::test_cc_complete_via_mcp`
- `tests/test_mcp_tools.py::test_cc_register_via_mcp`

Both fail with `Error: refusing to register an untracked task file (no-repo)` —
Lane 3's new git guard in `seldon/commands/cc.py` (see its new
`tests/test_cc_git_guard.py`), which `tests/test_mcp_tools.py` has not been
updated for. Neither file is in this lane's scope. All 73 ontology/parser tests
pass.

---

## 5. Live repair of the `seldon-ontology` master

### 5a. Snapshot first

Full JSON snapshot of master (meta, all 105 term nodes with every property, all
36 relationships) taken **before** any write, and a second one after:

```
scratchpad/lane4/master_BEFORE.json   epoch 3, 105 terms, all active, 36 rels
scratchpad/lane4/master_AFTER.json    epoch 4, 105 terms, 103 active + 2 deprecated, 36 rels
```

All commands were run through the **worktree's** code, not the installed console
script, via a `CliRunner` harness that prints its own code provenance before
running:

```
parser  : /Users/brock/.../worktrees/defect-fixes-ad028/seldon/ontology/parser.py
ontology: /Users/brock/.../worktrees/defect-fixes-ad028/seldon/commands/ontology.py
has SECTION_COVERAGE: True
```

### 5b. Dry run — and a third correction to the brief

The brief predicted "the 5 real terms ADDED and exactly 2 deprecation
candidates." The additions half is wrong, and the reason matters.

The five real terms were **created in master at epoch 1**, from the *pre-b6714f3
table*, before the regression existed. They have been sitting in master ever
since, `active`, with their March definitions, orphaned from their source. Lane 2
observed exactly this and correctly refused to deprecate them. So they are
**updates**, not creates: the fix reconnects them to the markdown and refreshes
their now-stale definitions.

```
$ seldon ontology ingest --dry-run          # worktree code, live master
Parsed 51 terms, 36 relationships   (validity;    was 48 — minus 2 junk, plus 5 real)
Parsed 52 terms, 0 relationships    (practitioner; unchanged)
Total: 103 terms, 36 relationships across 2 files.

[DRY RUN] Change plan against the master database:
  Create:    0 terms
  Update:    5 terms
    ~ ontology:validity:related:compaction        Compaction
    ~ ontology:validity:related:context_window    Context window
    ~ ontology:validity:related:fidelity          Fidelity
    ~ ontology:validity:related:handoff_document  Handoff document
    ~ ontology:validity:related:state             State
  Unchanged: 98 terms
  New relationships: 0
  Would deprecate (needs --deprecate-missing): 2 terms
    - ontology:validity:related:log_precision_fitness  Log-precision fitness
    - ontology:validity:related:precision_gain_rate    Precision gain rate

Master epoch would move 3 -> 4 and one ontology_ingested event would be written.
No changes written.
```

**Judgment to proceed.** The load-bearing half of the expectation — *exactly two
deprecation candidates, both the `leibniz-pi` junk* — held precisely. The
create/update difference is fully explained by master state that predates the
regression and is already documented in
`cc_tasks/2026-09-04_ontology_ingest_defects_SUBRESULT.md` §4 (master epoch 3,
105 terms, those same five reported as orphans). Nothing unexpected, nothing
broad, no mass deprecation. Master was snapshotted. Proceeded.

Definition drift confirming the updates are real, not spurious:

| term | master (epoch 1, table) | source (definition list) |
|---|---|---|
| `context_window` | "The token buffer containing the system's current operative state — the literal instrument in LLM pipelines" | "The mutable content that accumulates during pipeline operation — the literal instrument in LLM pipelines (combined with fixed model weights). See Core Construct entry above…" |

### 5c. Live run

```
$ seldon ontology ingest --deprecate-missing     # worktree code, live master
Total: 103 terms, 36 relationships across 2 files.
Master epoch 4: Ingested 0 new, updated 5, unchanged 98 terms.
0 relationships created. 2 deprecated.
```

| | before | after |
|---|---|---|
| master epoch | **3** | **4** |
| term nodes | 105 | 105 |
| `active` | 105 | 103 |
| `deprecated` | 0 | 2 |
| relationships | 36 | 36 (byte-identical) |

Snapshot diff — **exactly seven nodes touched, nothing else, no node added or
removed**:

```
only in BEFORE: []
only in AFTER : []
relationships identical: True
CHANGED ...:related:compaction            fields [content_hash, definition, epoch, source_vocabulary, updated_at]   active -> active
CHANGED ...:related:context_window        fields [content_hash, definition, epoch, source_vocabulary, updated_at]   active -> active
CHANGED ...:related:fidelity              fields [content_hash, definition, epoch, source_vocabulary, updated_at]   active -> active
CHANGED ...:related:handoff_document      fields [content_hash, definition, epoch, source_vocabulary, updated_at]   active -> active
CHANGED ...:related:state                 fields [content_hash, definition, epoch, extra, source_vocabulary, updated_at]  active -> active
CHANGED ...:related:log_precision_fitness fields [state, updated_at]                                                active -> deprecated
CHANGED ...:related:precision_gain_rate   fields [state, updated_at]                                                active -> deprecated
```

Events appended to the worktree's `seldon_events.jsonl` (1705 → 1709 lines):
two `artifact_state_changed` (active → deprecated, `artifact_type: OntologyTerm`),
one `ontology_ingested` (`master_epoch: 4`), one `ontology_synced`.

### 5d. Sync — `seldon-seldon-self` only

```
$ seldon ontology sync                            # worktree code
Synced to epoch 4: 0 new, 5 updated, 2 deprecated. Project is current.
```

Replica verification:

```
ontology:validity:related:compaction        active     epoch=4  'Automated summarization/truncation of context to fit window …'
ontology:validity:related:context_window    active     epoch=4  'The mutable content that accumulates during pipeline operati…'
ontology:validity:related:fidelity          active     epoch=4  'Faithfulness of the operative state to the actual history of…'
ontology:validity:related:handoff_document  active     epoch=4  'Explicit serialization of accumulated state for session cont…'
ontology:validity:related:state             active     epoch=4  'The accumulated working context: decisions made, terms defin…'
ontology:validity:related:log_precision_fitness  deprecated  epoch=2  'leibniz-pi'
ontology:validity:related:precision_gain_rate    deprecated  epoch=2  'leibniz-pi'
```

No other project database was written to.

---

## 6. Replica status — the junk is still live in 13 other projects

Read-only survey of every online database (no writes):

| database | replica epoch | terms | junk terms | 5 real terms active |
|---|---|---|---|---|
| `seldon-ontology` (master) | — (epoch 4) | 105 | **deprecated** | 5 |
| `seldon-seldon-self` | **4** | 105 | **deprecated** | 5 |
| `seldon-ai-readiness-kg` | 3 | 105 | active | 5 |
| `seldon-ai-workflow-design` | 3 | 105 | active | 5 |
| `seldon-blank` | 3 | 105 | active | 5 |
| `seldon-book-responsible-ai` | 3 | 105 | active | 5 |
| `seldon-brock-projects` | 3 | 105 | active | 5 |
| `seldon-census-web-concept-inventory` | 3 | 105 | active | 5 |
| `seldon-federal-survey-concept-mapper` | 3 | 105 | active | 5 |
| `seldon-icsp-notebook` | 3 | 105 | active | 5 |
| `seldon-nsf-aiday2026` | 3 | 105 | active | 5 |
| `seldon-tickbiterisk` | 3 | 105 | active | 5 |
| `seldon-usai-harness` | 3 | 105 | active | 5 |
| `seldon-sfv-paper` | 2 | 53 | active | 5 |
| `seldon-test-project` | 1 | 48 | active | 0 |

**13 project replicas still carry both `leibniz-pi` terms as `active`.**

**What is needed to clean them:** nothing but a sync. Each project needs

```bash
cd /path/to/<project>          # a directory with its own seldon.yaml
seldon ontology sync
```

which will report `0 new, 5 updated, 2 deprecated` and move that replica to epoch
4. Lane 2's `sync` already propagates deprecation to existing replica terms and
declines to introduce a deprecated term into a replica that never had one
(`tests/test_ontology_ingest_lifecycle.py::TestSyncPropagatesDeprecation`), so
the operation is safe and idempotent. It is not run here: the brief scoped this
lane to `seldon-seldon-self`, and each project's sync should land in that
project's own event log.

Two rows deserve a second look when someone gets to them:

- `seldon-sfv-paper` at epoch 2 with 53 terms — it never received the epoch-3
  practitioner vocabulary.
- `seldon-test-project` at epoch 1 with 48 terms and **zero** of the five real
  related terms — it is a stale test artifact holding a pre-b6714f3 parse. It may
  simply want dropping.

---

## 7. Things this brief got wrong, and other findings

1. **The commit is `b6714f3` (2026-03-28), not `62d6bdf` (2026-04-17).** §1a.
   The exposure window is five months, not four.
2. **The five terms are not "missing from the graph."** They are present in
   master, `active`, with stale epoch-1 definitions. They were missing from the
   *parse*, which made them look like orphans. The live plan is therefore 0
   creates and 5 updates, not 5 adds. §5b.
3. **The identical unbounded-scan idiom existed in seven parsers, not one.** Only
   Related Terms had leaked, because only its section stopped containing a table.
   All seven are now bounded. §2a.
4. **Three sections of the vocabulary are parsed by nobody at all** — a separate,
   pre-existing gap of the same family, found by the coverage test and left
   unfixed on purpose so the live dry run would match the brief's expectation:

   | section | unparsed term definitions |
   |---|---|
   | `## Core Instrument Terms` | accumulated state, operative state, composite instrument, token limit, instrument stability assumption |
   | `## Framework Terms (Cross-Cutting)` | bounded agency |
   | `### Core Construct: Context Window` | the full "context window" entry (a shorter version is picked up via Related Terms) |

   All six terms were added by `62d6bdf`, are enforced by
   `ontology/validity/vocabulary_rules.yaml` for glossary checking, and have
   never existed in the graph. They are declared `(None, 0)` in
   `SECTION_COVERAGE` with a comment so the gap is attributable rather than
   invisible. **Recommend a follow-up task** to claim these sections — it is
   roughly ten lines using the now-existing `_parse_definition_list`, but it
   adds six terms to the shared master and deserves its own dry-run review.
5. **`seldon.yaml:16` hardcodes an absolute vocabulary source path**
   (`source: /Users/brock/GitHub/seldon/ontology/`). Every ingest run from this
   worktree therefore read the **main checkout's** markdown, not the worktree's.
   Harmless here — both files are byte-identical (`md5 e97109538a0c…` and
   `5b700ff22c2d…`) and my changes were to the parser, not the vocabulary — but
   it means a worktree cannot test a vocabulary edit without editing the main
   checkout. Violates repo standards §2 (never hardcode paths). Not fixed:
   `seldon.yaml` is outside this lane's scope.
6. **Replica epoch lives on `_OntologyReplicaMeta.last_epoch`**, not
   `_OntologyMeta.epoch`. Noted because the obvious query returns `None` for
   every replica and reads as "never synced."

---

## 8. Files changed

| File | Change |
|---|---|
| `seldon/ontology/parser.py` | Bounded section scanning; `_parse_related_terms` rewritten for definition lists; `SECTION_COVERAGE` + `_PARSER_CATEGORY` + `_check_section_yields`; `VocabularyParseError`; module docstring records the regression |
| `tests/test_parser_sections.py` | **New.** 19 tests: the specific regression, section boundaries, coverage declaration |
| `tests/test_ontology.py` | Added `TestParser::test_parse_related_terms` |
| `tests/test_ontology_ingest_lifecycle.py` | Orphan fixture repointed from a junk table row to a real term |

Not touched: `seldon/commands/ontology.py` (Lane 2's), `seldon/commands/verify.py`,
`seldon/commands/cc.py`, `seldon/core/**`, `tests/conftest.py`, `tests/testdb.py`,
`docs/design/**`, `ontology/**` (the markdown was correct; the parser was wrong).

Not done, per instructions: no commit, no graph task closed.
