# SUBRESULT — Lane B: resolver caller options + reference-token name grammar

**Date:** 2026-09-04
**Worktree:** `.claude/worktrees/open-defect-closeout` (branch `main`, uncommitted)
**Graph tasks:** `f6b32bbe` (resolver options), `3376805b` (placeholder regex defect)
**Files changed:** `seldon/paper/build.py` (only source file touched)
**Files added:** `tests/test_resolver_options.py`, `tests/test_reference_pattern.py`
**Suite:** `1368 passed` in 79s — 43 of them new here. Zero failures.

---

## 1. Suite count and a contradicted premise

The task brief states the baseline is **1296 passed** and that I should finish at
1296 + my new tests (= 1339). Live state says otherwise: the suite collects
**1368**, of which **43** are mine, so the pre-existing count in this worktree
was **1325**, not 1296.

The 29-test difference is not mine and is not a regression: the shared worktree
carries other lanes' uncommitted work, including four untracked new test files
(`tests/test_legacy_events.py`, `tests/test_projects_discovery.py`,
`tests/test_replay_check.py`, `tests/test_verify_event_log.py`) plus edits to
`tests/test_authoring_workflow.py`. The whole suite is green, so nothing is
masked by the discrepancy — the "1296" figure was simply stale by the time Lane B
started.

Command used throughout (never `source .env && pytest`):

```
python -m dotenv -f .env run -- python -m pytest tests/ -q
```

CLI verification used `python -m seldon`, confirmed to resolve to
`.../worktrees/open-defect-closeout/seldon/__init__.py`, not the main checkout.

---

## 2. Task `f6b32bbe` — two caller options on `resolve_references`

Shipped, both on `seldon/paper/build.py::resolve_references`, both defaulting to
exactly today's behaviour:

| Option | Default | Effect |
|---|---|---|
| `mark_proposed: bool` | `True` | When `False`, a value admitted by `allow_proposed` renders bare, with no `(proposed)` suffix. |
| `value_formatter: Callable[[Any], str]` | `str` | Applied to the resolved field value to produce the rendered string, in every path including the proposed-marker path. |

Two decisions worth recording:

**The SI-03 warning is still emitted under `mark_proposed=False`, and its message
changes to say what actually happened** ("rendered without a marker
(--allow-proposed, mark_proposed=False)"). This is what makes suppressing the
marker acceptable rather than lossy: the downstream shim's own justification was
"the information is not lost — the proposed count is reported by `--check`", and
that claim only holds if the library keeps reporting the tokens. It does;
`summarize_proposed` still counts and names them. A test pins this.

**A `value_formatter` that returns a non-`str` raises `TypeError` naming the
token and file**, rather than being recorded as a `RefError`. That is a caller
bug, not a document problem, and letting it fall through to `re.sub` would raise
deep in the regex machinery with no reference to the token that caused it. The
docstring's `Raises:` section was updated from "Nothing" accordingly — it is no
longer true that the function raises nothing.

`build_paper` and the `seldon paper build` CLI were deliberately **not** given
new flags. The two options are a library contract for programmatic callers (the
ai-readiness-kg shim calls `resolve_references` directly); adding CLI surface for
them was not asked for and would be speculative.

### The two shim-workaround tests

`tests/test_resolver_options.py` — the file's module docstring names the shim,
the two lies it told the library, and the removal condition recorded in
`ai-readiness-kg/scripts/g1_resolve_results.py`.

1. `test_value_formatter_renders_integral_float_without_trailing_zero` —
   an artifact node holding `value=26.0` renders as `"there are 26 rows"` via a
   formatter copied from the shim's `_render_value`. Asserts additionally that
   `artifacts["result:count"]["value"] == 26.0` afterwards, i.e. **the index was
   not pre-rendered** — which is precisely workaround 1 becoming unnecessary.

2. `test_mark_proposed_false_renders_bare_value_from_a_proposed_result` — a node
   with `state="proposed"` renders `"7.5"`, `PROPOSED_MARKER not in resolved`,
   and asserts `artifacts["result:rate"]["state"] == "proposed"` afterwards, i.e.
   **the state was not faked as accepted** — workaround 2 becoming unnecessary.

3. `test_both_options_reproduce_the_shim_output_without_doctoring_the_index` —
   the composite: the real ai-readiness-kg case (proposed Result, integral float)
   renders `"The gate admitted 26 documents."` and the artifact dict is asserted
   equal to the undoctored node.

Plus default-preservation tests (`value_formatter` defaults to `str` → `26.0`;
`mark_proposed` defaults to `True` → `7.5 (proposed)`), a test that
`mark_proposed=False` alone does **not** admit a proposed Result (`allow_proposed`
still gates entry, SI-03 still fatal), and the loud-failure test.

---

## 3. Task `3376805b` — `REFERENCE_PATTERN` now uses the AD-028 name grammar

**Before:** `\{\{(result|figure|cite):([^:}]+):([^}]+)\}\}`
**After:** name capture is `RESULT_NAME_PATTERN`'s body with its anchors
stripped, giving `\{\{(result|figure|cite):([A-Za-z0-9][A-Za-z0-9_.-]*):([^}]+)\}\}`
at runtime.

The placeholder is now **correctly not a token**: `{{result:<NAME>:value}}` does
not match, `{{result:G1_x:value}}` does (uppercase-leading, so the test also pins
that the 2026-09-04 amendment to AD-028 §1 is wired into `REFERENCE_PATTERN` and
not only into `seldon result register`). `resolve_references` on prose containing
the placeholder returns the text unchanged with `errors == []` — no SI-01, no
pre-filter needed downstream.

### The grammar is derived, never copied

`RESULT_NAME_PATTERN` has one definition point by AD-028, and
`tests/test_result_grammar.py::test_result_name_pattern_appears_in_exactly_one_file`
greps the whole repo (tests/ included, not exempt) for the literal pattern string
and asserts exactly one hit. Neither `build.py` nor either new test file writes
the grammar. `_unanchored_name_grammar()` imports the constant and strips
`^`/`$`, raising `ValueError` if the constant ever stops being fully anchored —
because silently embedding a stray anchor inside `REFERENCE_PATTERN` would make
every token stop matching. That grep test still passes.

### Cross-lane need — the import cycle (this is the one thing to hand on)

The brief said to *import* `RESULT_NAME_PATTERN` rather than copy or move it.
**That premise is contradicted by live state: an eager import is a hard circular
import, and it fails in both directions.** `seldon/commands/result.py` line 25
does `from seldon.paper.build import REFERENCE_PATTERN` at module top level,
*above* its own definition of `RESULT_NAME_PATTERN` at line 37. Verified
empirically, not reasoned about:

- import `seldon.paper.build` first → `ImportError: cannot import name 'REFERENCE_PATTERN' from partially initialized module 'seldon.paper.build'`
- import `seldon.commands.result` first → `ImportError: cannot import name 'RESULT_NAME_PATTERN' from partially initialized module 'seldon.commands.result'`

Every eager arrangement I checked fails: PEP 562 module `__getattr__` fails too
(result.py's `from ... import` triggers it while result.py is still partial), and
a define-early-then-rebind scheme is worse than failing — it would leave
`result.py` permanently bound to the *permissive* pattern while `build.py` used
the narrow one, a silent divergence between two modules that check the same
documents.

What shipped instead, entirely inside my own file: `REFERENCE_PATTERN` is a
`_LazyReferencePattern` — a `__getattr__`-delegating wrapper that compiles on
first *use* rather than at import. Import-time binding touches no grammar, so the
cycle never closes; by the time any `.finditer`/`.sub`/`.findall`/`.pattern`
access happens, both modules are fully loaded. A test drives all four accessors
and a second test spawns two subprocesses importing in each order.

**The cross-lane need:** the wrapper exists only because the grammar constant
lives in a CLI command module that itself depends on the paper package. The
correct fix is to hoist `RESULT_NAME_PATTERN` (with `RESULT_NAME_MAX_LENGTH` and
`RESULT_NAME_GRAMMAR_PROSE`) into a leaf module both can import — and to update
`DEFINITION_POINT` in `tests/test_result_grammar.py` to follow it. That touches
`seldon/commands/result.py` and `tests/test_result_grammar.py`, neither of which
Lane B owns, so I did not reach across. The removal condition is written into the
`_LazyReferencePattern` docstring: after the hoist, the whole class collapses back
to a module-level `re.compile(...)`.

### `figure` and `cite` names — what I found and what I did

I checked before narrowing, because narrowing `cite` to a Result-name grammar
could in principle stop matching valid BibTeX-style keys.

**Every `figure` and `cite` token name in this repo** (fixtures, tests, docs,
templates) already conforms to the Result grammar: `F1`, `fig_a`, `fig1`,
`fig_convergence`, `my_fig`, `X` for figures; `A2020`, `a2020`, `B2021`,
`Jones2019`, `smith2020`, `Smith2020`, `smith_2023`, `key`, `X` for cites. A
repo-wide sweep for three-part tokens whose name violates the grammar returned
**exactly one hit**, and it is the cc_task spec file itself quoting
`{{result:<n>:value}}` as the thing to reject.

**The decisive point is structural, not statistical.** A `cite` token names a
**Citation artifact**, not a BibTeX key. The BibTeX key is a separate property,
`bibtex_key`, on that artifact — which is exactly what the SI-07 check reads and
compares against `references.bib`. So the token grammar constrains Seldon
artifact names only; a BibTeX key containing `:`, `/`, `+` or anything else is
untouched by this change. (Note a key containing `:` was already unreachable
under the *old* pattern, since `[^:}]+` excluded it.) The same holds for
`figure`: the name is a Figure artifact's name and the file path lives in its
`path` property.

**Decision: all three token types share the grammar.** They are all artifact
names, so a per-type grammar would be an unmotivated special case — and the
placeholder defect is not `result`-specific: `{{figure:<NAME>:path}}` and
`{{cite:<NAME>:bibtex_key}}` were equally misreported, and both are now correctly
not tokens. Tests cover matching for real figure/cite names and non-matching for
their placeholders.

### Out of scope, noted rather than fixed

- **The `FIELD` capture is still `[^}]+`.** So `{{result:NAME:FIELD}}` — a
  placeholder with a *legal* name (`NAME` is grammar-legal) — still matches and
  still reports SI-01. This is unchanged behaviour and it matches the downstream
  shim's own grammar, which would also match it. The reported defect is
  specifically the name position and specifically the angle-bracket form. A
  future task could narrow the field capture to a field-name grammar; that is a
  different decision with a different blast radius.
- **`XREF_PATTERN` in `seldon/paper/numbering.py`** (the two-part
  `{{figure:NAME}}` / `{{table:NAME}}` / `{{section:NAME}}` form) still uses
  `[^:}]+`. I did not touch it: it is a different pattern in a file I do not own,
  and it surfaces no defect, because `resolve_xref_tokens` leaves an unknown name
  as-is and records no error. Narrowing it would be consistency work, not a fix.

---

## 4. Downstream follow-up (not actionable from this repo)

Once this lands, `ai-readiness-kg/scripts/g1_resolve_results.py` can drop all
three of its adaptations: `TOKEN_RE` (its private stricter grammar and the
pre-filter that goes with it), `_ACCEPTED_STATE = "verified"` (the faked state),
and the pre-rendering of `_render_value` into the index it hands the library. The
shim's calls become
`resolve_references(..., allow_proposed=True, mark_proposed=False, value_formatter=_render_value)`
against `REFERENCE_PATTERN` directly. That shim's docstring names both this task
and the removal condition, so the trail closes from both ends.

## 5. Not done, by instruction

No commit. No graph task closed. `seldon/commands/result.py`,
`seldon/ontology/**`, `seldon/paths.py`, `seldon.yaml`, `seldon/core/**`,
`tests/conftest.py`, `tests/testdb.py` and `tests/test_result_grammar.py` were
read but not edited. `seldon/commands/paper.py` was in scope but needed no change.
