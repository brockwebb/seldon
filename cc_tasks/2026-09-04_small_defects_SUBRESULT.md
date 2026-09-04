# SUBRESULT — Small defects from the 2026-09-04 sweep RESULT §7 (Lane S)

**Date:** 2026-09-04
**Graph task:** `0977c79a`
**Worktree:** `/Users/brock/GitHub/seldon/.claude/worktrees/open-defect-closeout`
**Lane:** S — ontology parser, paths, `python -m seldon`, term content hash
**Concurrent lane:** B, on `seldon/paper/build.py`, `seldon/commands/paper.py`,
`tests/test_paper_build.py`. Not touched here.

Four defects recorded but not fixed by the 2026-09-04 defect sweep
(`cc_tasks/2026-09-03_seldon_defect_sweep_registry_lifecycle_ontology_RESULT.md`
§7, items 2, 4, 5, 6). All four are now fixed. Executed in the order (b), (c),
(a), (d) so that the two live epoch moves are individually attributable.

---

## 0. Suite

| | count |
|---|---|
| Baseline in this worktree at session start | **1302 passed** |
| New tests added by this lane | **+35** |
| Final, full suite | **1380 passed, 0 failed** |

Two premises about the count were wrong; see §6.1. The brief stated 1296; the
worktree was at **1302** before this lane changed anything. And the final total
is not 1302 + 35: the other lanes are committing into the *same* worktree
throughout, so the absolute number moved under this lane by 43 tests that are
not its own (1302 + 35 + 43 = 1380). The number this lane can vouch for is its
own four files:

| file | tests before | tests after |
|---|---|---|
| `tests/test_main_module.py` *(new)* | — | 5 |
| `tests/test_paths_ontology_root.py` *(new)* | — | 11 |
| `tests/test_parser_sections.py` | 20 | 27 |
| `tests/test_ontology_ingest_lifecycle.py` | 25 | 37 |
| **total** | **45** | **80** |

Zero failures originate in this lane. One transient failure was observed in an
intermediate full run and is attributed elsewhere; see §6.5.

---

## 1. Item (b) — `python -m seldon` was broken

**Shipped:** `seldon/__main__.py` — a thin shim importing `main` from
`seldon/cli.py`.

`seldon/commands/verify.py` shells out with `[sys.executable, "-m", "seldon",
...]` in `_fix_file_hashes` (line 1188) and `_fix_ontology` (line 1202). That
form is deliberate: `sys.executable` plus `-m` guarantees the child runs the
same interpreter and the same checkout as the parent, whereas the `seldon`
console script resolves through whatever install is on `PATH`. With no
`__main__` module both raised `CalledProcessError`, so **`verify --fix` silently
did neither sync**.

The shim is deliberately empty of logic. `cli.py` stays the single definition of
the command set; a second `click.group()` here would let `python -m seldon` and
`seldon` diverge, which is the failure the shim exists to prevent.
`test_python_m_seldon_exposes_the_same_commands_as_the_console_script` enforces
that by comparing `--help` output against `seldon.cli.main.commands`.

**Proof:**

```
$ python -m seldon --help
Usage: python -m seldon [OPTIONS] COMMAND [ARGS]...

  Seldon — AI-assisted research artifact tracker.
...
```

`tests/test_main_module.py` runs the real subprocess rather than importing
`seldon.__main__`; importing would not have caught the original defect, because
the failure was that `runpy` could not find the module.

---

## 2. Item (c) — hardcoded ontology source in `seldon.yaml`

**Shipped:**

1. `seldon.yaml` line 16: `source: /Users/brock/GitHub/seldon/ontology/` →
   `source: ontology/`.
2. `seldon/paths.py`: new `resolve_ontology_root(configured_source, project_dir)`.
3. `seldon/commands/ontology.py::_resolve_vocabulary_paths()` now joins
   `shared_ontology.vocabularies` onto that resolved root instead of calling
   `get_shared_ontology_sources()`.

### 2.1 The design decision, and why it is both halves

The brief offered three options: make the resolver fall back to
`seldon/paths.py` when the configured path is missing, rewrite the config value,
or both. **Both — and the two are not redundant, because neither one alone
satisfies the requirement.**

* **The fallback alone does not fix the worktree case.** This is the decisive
  point. `/Users/brock/GitHub/seldon/ontology/` **exists** when read from a
  worktree — it is the main checkout's tree. A "fall back when the configured
  path is missing" rule therefore never fires, and the worktree keeps silently
  reading the main checkout's vocabulary. The symptom of this defect was never
  an error; it was a wrong answer. A fallback keyed on absence cannot see it.
* **The config rewrite alone leaves a real failure mode open.** A project whose
  absolute `source` names a checkout that has since moved or been renamed gets
  `Cannot locate vocabulary file` — recoverable only by hand-editing config. The
  ontology tree ships beside the installed package, so the correct answer is
  derivable; refusing to derive it is the "bad string beats no default" pattern
  `seldon/paths.py` was written to end.

So: relative `source` resolved **against the directory holding `seldon.yaml`**
(not the process CWD, so the answer does not depend on where the command was
launched), with a marker-checked fallback to
`distribution_root() / "ontology"` when the configured tree is absent.

### 2.2 Why the resolution lives in `ontology.py`, not `config.py`

`get_shared_ontology_sources(config)` takes only the parsed dict — it has no
project directory to resolve a relative path against, so making it project-root
relative means a signature change, and its other caller is
`seldon/commands/paper.py`, which belongs to Lane B. It is left untouched. It
keeps working with the new relative `source` because both of its callers already
establish `project_dir = Path.cwd()` before `load_project_config()`; verified
live (§5.4).

The env-var semantics are unchanged and are deliberately *not* unified:
`SELDON_ONTOLOGY_PATH` names a single vocabulary **file** to
`_resolve_vocabulary_paths` and the ontology **root directory** to
`seldon/paths.py`. The two never meet — the env branch in
`_resolve_vocabulary_paths` returns before any `seldon.paths` call — and that is
now stated in a comment at the branch.

### 2.3 Proof

```
$ python -c "import sys; sys.path.insert(0,'.'); \
    from seldon.commands.ontology import _resolve_vocabulary_paths; \
    print(*_resolve_vocabulary_paths(), sep='\n')"
/Users/brock/GitHub/seldon/.claude/worktrees/open-defect-closeout/ontology/validity/VALIDITY_VOCABULARY.md
/Users/brock/GitHub/seldon/.claude/worktrees/open-defect-closeout/ontology/practitioner/PRACTITIONER_VOCABULARY.md
```

and every live ingest below printed the worktree's own paths.
`tests/test_paths_ontology_root.py` pins the property directly: two synthetic
checkouts carrying the *same* config resolve to *different* trees
(`test_two_checkouts_of_the_same_config_resolve_to_different_trees`), and
`TestSeldonYamlIsNotHardcoded` fails if an absolute path ever returns to
`seldon.yaml`.

---

## 3. Item (a) — three sections parsed by nobody

**Shipped:** `seldon/ontology/parser.py`

* `_parse_definition_list_section(lines, heading, id_segment, category)` — one
  bounded definition-list reader, since three sections share the exact shape.
  `_parse_related_terms` is now a call into it, so there is one implementation,
  not three.
* `_parse_core_instrument_terms` → `## Core Instrument Terms`,
  `category="core_instrument_term"`, ids `ontology:validity:instrument:*`.
* `_parse_cross_cutting_terms` → `## Framework Terms (Cross-Cutting)`,
  `category="cross_cutting_term"`, ids `ontology:validity:crosscutting:*`.
* `SECTION_COVERAGE`: the two `##` sections move from `(None, 0)` to
  `("_parse_core_instrument_terms", 5)` and `("_parse_cross_cutting_terms", 1)`;
  `_PARSER_CATEGORY` gains both; `parse_vocabulary` composes them into
  `all_terms`; the `ParsedTerm.category` docstring lists the two new categories.

Both heading matches are **exact, not prefix**: `## Framework Terms` is a strict
prefix of `## Framework Terms (Cross-Cutting)`, so a prefix match in either
parser would silently merge the two sections.
`test_cross_cutting_section_does_not_collide_with_framework_terms` pins it.

### 3.1 The six terms

Parsed count went 51 → 57 for the validity vocabulary; 103 → 109 active terms in
master.

| term_id | name | definition (verbatim, markdown stripped) |
|---|---|---|
| `ontology:validity:instrument:accumulated_state` | Accumulated state | The content that has built up inside the context window over sequential operations: decisions, terminology, parameters, intermediate findings considered cumulatively. Use when emphasizing history across operations. Distinguished from operative state (which is accumulated state at a specific moment). |
| `ontology:validity:instrument:operative_state` | Operative state | The accumulated state at a specific point in time, as actively referenced by the pipeline in a current operation. Use when emphasizing what the pipeline is currently operating on, especially at points of computation, reconciliation, or session boundaries. |
| `ontology:validity:instrument:composite_instrument` | Composite instrument | The combination of fixed model weights plus mutable context window that constitutes the measurement instrument in an AI-assisted pipeline. Unlike classical instruments, it changes with every interaction. |
| `ontology:validity:instrument:token_limit` | Token limit | The fixed architectural constraint on context window size, measured in tokens. An architectural constraint, not a mutable quantity. Distinct from context window content. |
| `ontology:validity:instrument:instrument_stability_assumption` | Instrument stability assumption | The shared assumption across all four classical validity types (construct, internal, external, statistical conclusion) that the measurement instrument is defined, stable, and consistent. SFV guards this assumption in AI-assisted pipelines, where the instrument (fixed weights + mutable context window) is not inherently stable. |
| `ontology:validity:crosscutting:bounded_agency` | Bounded agency | AI systems operate with constrained autonomy and persistent human oversight. AI provides analysis and recommendations; humans make consequential decisions and remain accountable. Contextual applications include AI-assisted research pipelines (section-level drafts and analyses), federal statistical applications (AI-assisted data processing and preliminary findings), and agentic frameworks (well-defined subtasks with defined scope and rollback capability). |

Each carries its `Do not write:` guidance in `extra["usage_note"]`, matching the
convention `_parse_related_terms` established; all six were verified present in
master with the note intact.

### 3.2 The third section is still `(None, 0)`, and that is now enforced

`### Core Construct: Context Window` was **deliberately left unparsed.** It
defines "Context window", which already reaches the graph as
`ontology:validity:related:context_window` via `_parse_related_terms`.
`seldon/commands/glossary.py::_render_glossary` emits one MyST `{glossary}` entry
per term keyed on `name`, so minting a second node would produce a duplicate term
description in every generated `glossary.md` — trading a silent absence for a
silent corruption.

This matches the sweep RESULT's own arithmetic: its §7.4 table counts 5 + 1 = the
**six** terms never in the graph, and describes the Core Construct row separately
as "a shorter version is picked up via Related Terms".

The reasoning is recorded beside the `(None, 0)` entry **and enforced** by
`test_context_window_is_not_minted_twice`, which asserts both the declaration and
the absence of any duplicate `name` across the whole parse — so the decision
cannot decay into an unnoticed omission.

**Follow-up, not taken here:** the Related Terms entry carries the *shorter* of
the two definitions and points at the Core Construct entry for the full one, so
the graph holds the weaker text. Promoting the fuller definition is an edit to
`ontology/validity/VALIDITY_VOCABULARY.md` — a vocabulary-content decision for
its author, not something a parser change may make. It is also arguably
mis-filed: a term defined in this very file should not sit under "Defined
Elsewhere".

---

## 4. Item (d) — `_term_content_hash` widened

**Shipped:** `seldon/commands/ontology.py`

```python
_TERM_HASH_VERSION = 2

payload = "|".join([
    f"v{_TERM_HASH_VERSION}",
    term.term_id, term.name, term.definition, term.category,
    json.dumps(list(term.citations or []), ensure_ascii=False),
    json.dumps(dict(term.extra or {}), sort_keys=True, ensure_ascii=False),
])
```

was `f"{term.term_id}|{term.definition}|{term.category}"`.

The hash is the *only* comparison ingest makes between a source term and master.
Every field outside it is a channel through which a vocabulary edit lands on disk
and never reaches the shared master or any replica, with no error. `name`,
`citations` and `extra` were all outside it, and all three are written to the
master node by `_term_to_props`. `extra["usage_note"]` holds the `Do not write:`
guidance for all six definition-list terms above, so this was a live drift
channel, not a theoretical one.

Design notes:

* **Citation order is significant** (document order is the order a replica
  renders); `extra` keys are **sorted**, so dict insertion order cannot change
  the digest.
* **The version prefix is inside the hashed payload on purpose.** Widening the
  definition of "changed" is itself a content-definition change; it must
  invalidate every stored hash and force one visible mass update rather than
  leaving v1 and v2 digests silently comparable. Bump `_TERM_HASH_VERSION`
  whenever the field set changes.
* `test_hash_covers_every_field_term_to_props_persists` asserts the invariant
  *structurally*: it enumerates what `_term_to_props` persists and fails if any
  term-sourced property has no declared variation, so the next added property
  cannot quietly become the next drift channel. `namespace` is explicitly
  excluded with its reason (a parser constant, not an editable field of the
  markdown).

### 4.1 Impact statement

| | |
|---|---|
| Dry-run plan | **0 creates, 109 updates, 0 unchanged**, 0 relationships, 0 deprecations |
| Live result | `Master epoch 6: Ingested 0 new, updated 109, unchanged 0` |
| Epoch | **5 → 6. Yes, this bumps the epoch.** |
| Replicas | **Yes, every replica will re-sync** on its next `seldon ontology sync`. |
| Acceptable? | **Yes.** |

109 rows is *every* active term in master (111 total, minus the 2 terminal
`deprecated` junk terms, which the source does not contain and which ingest
correctly left alone). The dry run was executed and its count read **before** the
live run.

Why the re-sync is acceptable:

1. A hash widening is a real content-definition change. The v1 hashes were
   *wrong* — they asserted "unchanged" about terms whose persisted content the
   graph had never verified. Re-stamping them is the correction, not collateral.
2. The re-sync writes **identical** term content; only `content_hash` and `epoch`
   move. No definition, name, category or citation changes value.
3. Per sweep RESULT §7.3 the 13 project replicas were **already stale** at epoch
   3, plus `seldon-sfv-paper` at 2 and `seldon-test-project` at 1. Every one of
   them needed a `sync` before this lane ran. The widening changes the target
   epoch they sync to, not whether they must sync.
4. A third ingest immediately afterwards reports `0 new, 0 updated, 109
   unchanged` and `Master epoch would stay 6 and no event would be written` — the
   migration is idempotent and the epoch is stable.

---

## 5. Live-write record — `seldon-ontology` master

Snapshots taken before every live write (full JSON of `_OntologyMeta`, all
`OntologyTerm` nodes and all inter-term relationships), under
`<scratchpad>/snapshots/`: `ontology_master_pre_A.json`,
`ontology_master_post_A.json`, `ontology_master_pre_D.json`,
`ontology_master_post_D.json`.

| step | epoch | terms | active | deprecated | why |
|---|---|---|---|---|---|
| start | **4** | 105 | 103 | 2 | as briefed |
| after (a) | **5** | 111 | 109 | 2 | 6 new terms created |
| after (d) | **6** | 111 | 109 | 2 | 109 content hashes recomputed |
| re-run | **6** | 111 | 109 | 2 | no-op, no event |

**The epoch moved exactly twice, once per item, each with its own
`ontology_ingested` event** in `seldon_events.jsonl`:

* `99285d9e-…` — `master_epoch: 5`, `new_terms: 6`, `updated_terms: 0`,
  `unchanged_terms: 103`
* `1dcf3f99-…` — `master_epoch: 6`, `new_terms: 0`, `updated_terms: 109`,
  `unchanged_terms: 0`

Both ingests ran as `python -m seldon ontology ingest` from the worktree root, so
they executed **this** checkout's code and read **this** checkout's vocabulary —
confirmed by printing `seldon.__file__` and by the source paths the command
echoed. That is items (b) and (c) in use.

---

## 6. Premises contradicted by live state

### 6.1 The stated baseline was wrong

The brief said **1296 passed**. The worktree was at **1302 passed** before this
lane changed anything (verified by a full run started before the first edit).
Six tests from another lane had already landed. A single absolute suite count is
in any case not a checkable claim in a shared worktree — three lanes are
committing into it concurrently, and 43 tests that are not this lane's landed
during the session. §0 states the per-file counts instead.

### 6.2 "6 real terms" is right, but "three sections" is not the same statement

The brief lists three unparsed sections and six terms. Those are consistent only
because the third section, `### Core Construct: Context Window`, defines a term
that is *already in the graph*. Parsing all three sections yields **seven**
terms, and the seventh is a duplicate `name`. Two sections were claimed; the
third stays declared-unparsed with an enforced reason. See §3.2.

### 6.3 `source_vocabulary` on master is provenance noise, and always was

Not in scope, found while verifying. Before this lane, the 105 master terms
carried **four different** `source_vocabulary` values — three absolute developer
paths from three different checkouts (including a long-dead worktree,
`/Users/brock/Documents/GitHub/seldon/.worktrees/feat-ad017-ontology/…`) and one
relative path. The property records the absolute path that happened to be
resolved at ingest time, so it has never identified anything stable.

This lane's runs replaced most of them with this worktree's path, which will
cease to exist when the worktree is removed. **No worse than before** — the value
was already a dead path for a third of the graph — but the fix is to store the
vocabulary path **relative to the ontology root** (`validity/VALIDITY_VOCABULARY.md`),
which is what the domain config's own example says it should be:

> `source_vocabulary` … "Source vocabulary path (e.g.,
> `'validity/VALIDITY_VOCABULARY.md'`)"

**Deliberately not fixed here.** It is a third mass update and a third epoch
bump, and the brief requires the two moves above to be individually attributable.
Recommend a follow-up task; it is a small change to `_term_to_props`' callers plus
one planned re-ingest, and it should ride along with any future hash version bump
so the two share a single migration.

### 6.4 The two junk terms are still present, correctly

`ontology:validity:related:log_precision_fitness` and
`:precision_gain_rate` remain in master as `deprecated` at epoch 2. `deprecated`
is terminal in the OntologyTerm state machine and the source does not contain
them, so both ingests correctly left them untouched. They are the reason 111
total ≠ 109 active.

### 6.5 One observed suite failure, not from this lane

An intermediate full run reported
`tests/test_result_grammar.py::test_result_name_pattern_appears_in_exactly_one_file`
failing with:

```
assert {'seldon/core/naming.py': 1} == {'seldon/commands/result.py': 1}
```

`RESULT_NAME_PATTERN` was being moved from `seldon/commands/result.py` to
`seldon/core/naming.py` by another lane while the run was in flight, so the test
read the file tree mid-move. Re-run alone immediately afterwards: **1 passed**.
No file in this lane's scope is involved.

---

## 7. Files changed

| file | item |
|---|---|
| `seldon/__main__.py` *(new)* | (b) |
| `seldon/paths.py` | (c) — `resolve_ontology_root` |
| `seldon.yaml` | (c) — relative `shared_ontology.source` |
| `seldon/commands/ontology.py` | (c) `_resolve_vocabulary_paths`; (d) `_TERM_HASH_VERSION`, `_term_content_hash` |
| `seldon/ontology/parser.py` | (a) — two parsers, shared definition-list helper, `SECTION_COVERAGE`, `_PARSER_CATEGORY`, `parse_vocabulary`, docstrings |
| `tests/test_main_module.py` *(new)* | (b) — 5 tests |
| `tests/test_paths_ontology_root.py` *(new)* | (c) — 11 tests |
| `tests/test_parser_sections.py` | (a) — +7 tests |
| `tests/test_ontology_ingest_lifecycle.py` | (d) — +12 tests |
| `seldon_events.jsonl` | two `ontology_ingested` events from the live ingests |

Not touched: any Lane B file, `seldon/core/**`, `seldon/commands/verify.py`,
`tests/conftest.py`, `tests/testdb.py`, `seldon/config.py`.

**Not done, per brief:** no commit, no graph task closed, no `seldon verify` run,
no replica `sync` executed. The 15 stale project replicas from sweep RESULT §7.3
still need `seldon ontology sync` from their own directories; they now sync to
epoch 6 instead of 4.
