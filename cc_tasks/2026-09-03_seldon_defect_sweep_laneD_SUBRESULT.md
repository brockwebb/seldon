# Lane D sub-RESULT — Small defects (`f951ed84`, `e3f751f6`, registrar description)

**Date:** 2026-09-03
**Project:** seldon (`/Users/brock/GitHub/seldon`)
**Parent task:** `cc_tasks/2026-09-03_seldon_defect_sweep_registry_lifecycle_ontology.md` §5
**Executed by:** CC (lane D subagent)

---

## 1. What shipped

### Files changed

| File | Change |
|------|--------|
| `seldon/paths.py` | **NEW.** Single place where every default path is derived from the installed package location. |
| `seldon/commands/go.py` | D1 handoff picker rewritten (`_handoff_sort_key`, `_find_latest_handoff`). D2: `_read_system_standards` no longer hardcodes `~/Documents/GitHub/CLAUDE.md`. |
| `seldon/commands/init.py` | D2: shared-ontology default resolved via `seldon.paths`; block omitted with a loud warning when no ontology tree exists; vocabulary list and inheritance mode lifted to named constants. |
| `seldon/commands/cc.py` | D3: description extraction rewritten (H1-first with boilerplate stripping, all-bold banner rejection); warning made source-aware; new `seldon cc rederive-description`. |
| `seldon.yaml` | D2: stale `Documents/GitHub` ontology source corrected to the real repo path. |
| `docs/templates/seldon_yaml_template.yaml` | D2: shipped template no longer carries one machine's absolute path; placeholder + note that `seldon init` fills it in. |
| `scripts/observability_collect.py` | D2: `GITHUB_ROOT` hardcode replaced by derived `SELDON_REPO_ROOT` / `PROJECTS_ROOT` (both env-overridable); stale path in a comment removed. |

### Tests added

| File | Content |
|------|---------|
| `tests/test_handoff_picker.py` | **NEW, 16 tests.** D1: same-date slug tie (both directions), date-prefix authority, hyphen/date-only prefixes, non-date digit runs, undated files, mixed directory with debris and subdirectories, empty/missing/`handoffs`-is-a-file, end-to-end through `assemble_go_context`. |
| `tests/test_cc_description.py` | **NEW, 26 tests.** D3: boilerplate stripping matrix, H1 precedence, all three observed failure shapes (em-dash H1, `**Task ID:**` metadata-first, truncated hard-wrapped prose), banner rejection on the fallback path, source-aware warning. |
| `tests/test_init.py` | **+21 tests.** D2: source scan of every default-producing file for the retired root *and* for any `/Users/<x>/` or `/home/<x>/` literal; shipped-template placeholder check; ontology resolution (derived, env override, bad override, wheel layout, marker validation); `seldon init` end-to-end assertions on the written `seldon.yaml`; system-standards resolution. |
| `tests/test_cc_utils.py` | 7 fixtures retitled (see §5). |

### Test counts

| Scope | Result |
|---|---|
| Lane-D modules, quiet machine | **168 / 168 passing** (`test_go`, `test_init`, `test_cc_utils`, `test_cc_complete`, `test_cc_spec_hash`, `test_cc_description`, `test_handoff_picker`) |
| Lane-D modules, 3–5 concurrent lane suites | 164–167 passing; every miss is a Neo4j-availability error or a shared-`seldon-test` wipe (§5.2), never a lane-D assertion |
| Full suite, final measured run | **861 passed / 73 failed** and **888 passed / 46 failed** on two consecutive runs — both meaningless (§5.2). Failures grouped by module: `test_task_lifecycle` 17, `test_ontology` 10, `test_mcp_tools` 8, `test_paper_sync` 4, `test_result` 3, `test_staleness` 2, `test_session_commands` 2. **Zero in any lane-D module.** |

Lane D adds **+63 tests** (16 handoff picker, 26 description, 21 init/paths); 7 existing `test_cc_utils` fixtures retitled, none deleted.

**The full-suite count is not measurable from this lane.** Three other lanes' pytest processes were live throughout (`ps` showed 3–5), and the tree also carries their uncommitted, not-yet-consumed `seldon/domain/research.yaml`. Integration must re-measure with no other pytest running.

---

## 2. D1 — the real root cause, with evidence

**Root cause: the picker sorted the whole filename descending, so for two handoffs written on the same day the trailing SLUG — which carries no recency information — decided the winner.**

Not "sorting was reversed" and not "mtime was ignored in general". Name-descending is in fact correct *across* dates for `YYYY-MM-DD_` prefixes; it fails only when the date component ties and the comparison spills into the slug.

Evidence — the actual directory, unchanged, as of this task
(`/Users/brock/GitHub/ai-readiness-kg/handoffs/`; the seldon repo's own `handoffs/` holds only April files, so the failure was observed in the downstream project):

```
-rw-r--r--  5230  Sep  1 13:23  2026-09-01_framework_deck_thread.md
-rw-r--r--  3399  Sep  2 17:46  2026-09-02_post_burn_reconciliation_and_g1_prior_art.md
-rw-r--r--  3070  Sep  2 13:42  2026-09-02_sensor_layer_and_june_consolidation.md
```

`sorted(names, reverse=True)[0]` → `2026-09-02_sensor_layer_and_june_consolidation.md`, because at the first differing character `s` > `p`. That file's own H1 is
`# Handoff — 2026-09-01/02: sensor layer, June consolidation, orientation-first`
— which is exactly the "09-01/02 handoff" the defect report says was served, while
`2026-09-02_post_burn_reconciliation_and_g1_prior_art.md` (four hours newer, `17:46` vs `13:42`) was the correct answer.

Ruled out, each by inspection of the same directory: no cached index exists (the function reads the directory every call); no non-date-prefixed file was present; no hidden/system file was present; no subdirectory was present. The failure needed none of those — the same-date pair alone is sufficient and was present.

**Fix as specified:** sort key is `(date_prefix, mtime)`. The `YYYY-MM-DD` prefix is authoritative because a handoff is *about* a session and may be written, corrected or copied later; mtime only breaks ties within a date. A file with no date prefix has no declared session date, so its mtime *date* stands in for one and it competes on mtime alone.

Two deliberate departures from a literal reading of the spec, both to make the rule total rather than partial:

1. The date-prefix regex is `^(\d{4}-\d{2}-\d{2})(?!\d)`, not `^\d{4}-\d{2}-\d{2}_`. Accepting `_`, `-`, `.` and end-of-name means `2026-09-02.md` and `2026-09-02-slug.md` are recognized; the negative lookahead still refuses to read a date out of `20260902_x.md`. Covered by three tests.
2. Dotfiles are excluded. A `.DS_Store` newer than every handoff would otherwise be readable as one. Covered by two tests.

Verified live after the fix:
- `_find_latest_handoff('/Users/brock/GitHub/ai-readiness-kg')` → `2026-09-03_g1_eval_program_v0_to_calibrated_v2.md` (correct — newest date).
- `_find_latest_handoff('/Users/brock/GitHub/seldon')` → `2026-04-18_session_close_75_bucket_shipped.md` (correct — the newer of the two 04-18 files by mtime).

---

## 3. D2 — the discrepancy, stated plainly

**The task file says `seldon init` "emits the retired `/Users/brock/Documents/GitHub/seldon/ontology` path". That is not what the code did. The picture is mixed, in three parts.**

**(a) The code default was already derived — and the derivation was still broken.**
`seldon/commands/init.py` already read `SELDON_ONTOLOGY_PATH`, else `Path(__file__).parent.parent.parent / "ontology"`. No literal path in the code. But the derivation is wrong for a wheel install: `ontology/` is **not** packaged (`pyproject.toml` ships only `seldon*` packages plus `seldon.domain` `*.yaml`), so on a non-editable install the expression yields `site-packages/ontology`, which does not exist, and `seldon init` would write a `shared_ontology.source` pointing at nothing. Every downstream reader (`seldon ontology sync`, `verify`, `paper audit`) then degrades quietly. **That is a real defect and it is fixed.**

This install is editable (`pip show seldon` → "Editable project location: `/Users/brock/Documents/GitHub/seldon`"), which is why the old derivation worked here at all — and it worked *through the `Documents` compatibility symlink named in the task*. `Path.resolve()` in the new code canonicalizes that away: the derived root is now `/Users/brock/GitHub/seldon`.

**(b) A near-miss the spec's phrasing would have walked into.**
"Package location → repo root → `ontology/`" has a collision: `seldon/ontology/` **already exists as a Python code package** (`parser.py`, `practitioner_parser.py` — the vocabulary parsers). A resolver that tries package-internal `ontology/` first finds that code directory on *every* install and "succeeds" with a directory containing no vocabulary. My first implementation did exactly this and the test caught it. The resolver now requires a **marker file** (`validity/VALIDITY_VOCABULARY.md`, the same constant `init` writes into `vocabularies`) before accepting a candidate as an ontology root. Regression test: `test_the_parser_code_package_is_never_the_vocabulary_root`.

**(c) The stale strings the task named do exist, and are fixed — plus one it did not name.**
- `seldon.yaml:16` → corrected to `/Users/brock/GitHub/seldon/ontology/`. (This file is a machine-specific generated config; an absolute path is correct here, the *retired* one was not.)
- `docs/templates/seldon_yaml_template.yaml:41` → replaced with `/ABSOLUTE/PATH/TO/seldon/ontology/` plus a note that `seldon init` fills it in.
- `scripts/observability_collect.py:30` → `GITHUB_ROOT` replaced with derived `SELDON_REPO_ROOT` (from the script's own location) and `PROJECTS_ROOT` (its parent), both env-overridable. Smoke-tested: discovers 15 projects under `/Users/brock/GitHub`, and `SELDON_REPO_ROOT/.env` resolves.
- **Not named in the task:** `seldon/commands/go.py::_read_system_standards` hardcoded `Path.home() / "Documents" / "GitHub" / "CLAUDE.md"` as its fallback — the same retired root, in a file lane D owns. It now derives `<distribution root>.parent / CLAUDE.md`, which resolves to the real `/Users/brock/GitHub/CLAUDE.md` (verified live, 15002 chars read). The old fallback was dead on this machine except through the symlink.

**Behaviour change to note:** when no ontology tree can be found, `seldon init` now writes `seldon.yaml` **without** a `shared_ontology` block and warns loudly on stderr naming `SELDON_ONTOLOGY_PATH`, rather than writing a path that cannot resolve. `init` already guards with `if "shared_ontology" in config_loaded`, so the omitted-block shape is supported. An explicit `SELDON_ONTOLOGY_PATH` that does not exist, or that names a file, is now a hard error before anything is written to disk.

**Test shape:** the D2 test does not assert one literal. It scans the source of every default-producing file (`seldon/paths.py`, `seldon/commands/init.py`, `seldon/commands/go.py`, `scripts/observability_collect.py`) and the shipped template for (i) the retired `Documents/GitHub` substring and (ii) **any** `/Users/<name>/` or `/home/<name>/` literal, then asserts the resolver's behaviour under four install layouts.

---

## 4. D3 — mechanism, before/after, and what the graph actually held

### The current parser had exactly one live defect; the other two shapes were already-fixed history

Confirmed empirically before changing anything (`_extract_description` on the real file):

- **Shape 1 — em-dash H1 (LIVE defect).** `_CC_TASK_TITLE_RE = ^CC Task(?:\s+\S+)?:\s*(.+)$` requires a **colon**. This repo titles with an em dash (`# CC Task — <subject>`), so the H1 branch missed. Extraction fell through to prose, where `**Immutable once written. Changes require a new task file…**` escapes `_METADATA_RE` (its `.` is outside the key character class) and became the description. Reproduced on the parent task file: current parser returned `'**Immutable once written. Changes require a new task file or an `_ADDENDUM-NN.md` sibling.**'`. This is the same shape as the seven ai-readiness-kg cases.
- **Shape 2 — `**Task ID:**` metadata-first (`7120e000`).** The *current* parser skips whole metadata blocks, so this shape no longer reproduces. The bad value in the graph is a stale artifact of an older parser version.
- **Shape 3 — truncated hard-wrapped prose (`676c0e39`).** The *current* parser joins wrapped paragraphs, so this shape no longer reproduces either. Also a stale value from an older parser.

**This is the load-bearing finding for the command:** two of the three named failures are not parser bugs any more; they are *frozen output* of parsers that were already fixed. Nothing re-reads a task file after registration, so a bad description is permanent. That is precisely why `rederive-description` is the deliverable, not just the parser change.

### Fix

`description := first H1's subject`, with `CC Task` / `Task` boilerplate stripped when a separator (`:`, `—`, `–`, `-`) follows, optionally with a task id (`CC Task T4:`). An H1 that is *only* boilerplate (`# CC Task`) names no subject and falls through. No H1 → first non-empty, non-metadata, **non-all-bold** paragraph → filename.

The `**...**` banner rule is the second half of the shape-1 fix: without it, a task file with no usable H1 still lands on the immutability notice. Tested independently of the H1 path.

### Before/after — `7120e000` and `676c0e39`: BLOCKED, premise contradicted

**Both source files are gone from disk and from git history.**

```
$ seldon cc rederive-description 7120e000
Error: source file missing on disk: cc_tasks/2026-04-16_file_issues_and_convention.md
  Artifact: 7120e000-2a20-4a87-b3b8-100efb3a1dbb
EXIT=1

$ seldon cc rederive-description 676c0e39
Error: source file missing on disk: cc_tasks/2026-05-07_ontology_tracer_bullet.md
  Artifact: 676c0e39-da69-4654-8450-78b10eba41be
EXIT=1
```

Verified: `git log --all --diff-filter=AD` finds no trace of either path (`cc_tasks/` was only tracked from commit `c53b3c9`, 2026-09-02 — everything earlier was untracked and has been deleted), and a filesystem search across `/Users/brock/GitHub` and `/Users/brock/Documents` finds neither file. Their descriptions remain, unchanged:

| Artifact | Description (unchanged) |
|---|---|
| `7120e000-2a20-4a87-b3b8-100efb3a1dbb` | ``**Task ID:** `seldon_file_issues_and_convention_2026-04-16` `` |
| `676c0e39-da69-4654-8450-78b10eba41be` | ``Add `tracer_bullet` as a named term to the master Seldon ontology with its`` |

The command fails loudly rather than guessing. **Integrator decision needed** (§7).

### Before/after — what WAS re-derived

A survey of all 49 registered CC tasks in `seldon-seldon-self` found 37 with missing source files, 3 unchanged, and 9 whose description the fixed parser improves. All 9 were re-derived live via `seldon cc rederive-description`, each writing an `artifact_updated` event (no Cypher `SET`, no history mutation):

| id | before | after |
|---|---|---|
| `0e36cfd7` | `register glossary ontology design note` | `Register Glossary-Ontology Architecture Gap Design Note` |
| `aec9ae0e` | `verify glossary path resolution` | ``Fix `seldon verify` Glossary Path Resolution`` |
| `3b1cf0ca` | ``` `seldon verify` currently runs 7 checks and exits with code 0 (clean), 1 (warnings), or 2 (issues)… ``` (truncated at 200) | ``Implement `seldon verify --strict` Mode`` |
| `c68e8da0` | ``**Parent ResearchTask:** `38b0698b` (Evolution Burst 2026-04 Plan Anchor)`` | `Measurement-Function Audit` |
| `ae99ef77` | ``**Parent ResearchTask:** `38b0698b` (Evolution Burst 2026-04 Plan Anchor)`` | `Wintermute Sleep-Function Architecture Specification` |
| `3a3cc98d` | ``**Parent handoff:** `handoffs/2026-04-18_phase_c_evolution_burst_closeout.md``` | `Register Phase C Synthesis Outputs and Close Evolution Burst` |
| `d369b7a3` | ``**Scope:** Investigation + fix in `seldon/config.py` and/or project initialization logic`` | `Investigate and Fix Cross-Project Graph Contamination` |
| `672ad2ac` | ``` `ResearchTask` has no honest terminal state for a task that is overtaken/obsoleted ``` | ``Add `superseded` terminal state to ResearchTask state machine`` |
| `bc2354f2` | `**Immutable once written. Changes require a new task file or an `_ADDENDUM-NN.md` sibling.**` | `Seldon defect sweep: Result registry contract, task lifecycle, ontology gaps, small defects` |

`bc2354f2` is **this task's own artifact** — a live instance of shape 1, now corrected.

None of the nine is on the parent task's "excluded on purpose" list. `e911fc13`, which is on that list, is in the missing-source-file set and was not touched.

### Second defect found while fixing the first: the warning was about to become noise

With the H1 now winning, `_description_looks_like_metadata` fired on `Seldon defect sweep: Result registry contract` — because `_METADATA_RE` matches any capitalized phrase followed by a colon, and `<topic>: <detail>` is the dominant title form in this repo. Every registration would have emitted a spurious `WARNING`, which trains the reader to ignore the warning that matters.

Fixed by making the warning **source-aware**: `_extract_description_with_source()` reports `h1` / `prose` / `filename`; a title-derived description is never flagged for metadata shape, a filename fallback is always flagged, and prose keeps the existing check. `_extract_description()` remains as a thin wrapper so existing callers are unaffected. The all-bold banner shape was also added to the metadata check. Three tests in `TestWarningIsSourceAware`.

---

## 5. Every other premise that live state contradicted

1. **"Baseline is 697 passing."** At the start of this lane the working tree was at **26 failed, 671 passed**. Verified against a pristine `HEAD` worktree (with the editable-install finder purged so the worktree's own `seldon` was imported): **696 passed, 1 failed** = 697 total. The 26 failures were caused by the integrator's uncommitted `seldon/domain/research.yaml` change (+55/−7: `Result.name`, `ResearchTask.terminal_reason`/`claimed_by`/`claimed_at`, `superseded_by`/`corrects`/`annotates`/`disputes` edges, `generated_by`/`computed_from` endpoint widening) landing before the lane code that consumes it. **Not caused by lane D, and not fixable from lane D — `seldon/domain/**` is read-only to this lane.**

2. **The suite is not safe to run concurrently across lanes — the single biggest obstacle to measuring anything.** Two distinct failure modes, both diagnosed to the environment:
   - `neo4j.exceptions.ClientError: Unable to load NODE …` and phantom empty results — `conftest.clean_test_db` runs `MATCH (n) DETACH DELETE n` against the **shared** `seldon-test` database, so two lanes running `pytest` delete each other's fixtures mid-test. The ontology tests likewise write to the **shared** `seldon-ontology` master.
   - `Failed: Neo4j not reachable but NEO4J_PASSWORD is set` from the session-scoped `neo4j_available` fixture — under 4–5 concurrent suites the server momentarily refuses connections and the fixture hard-fails, erroring out every Neo4j test in the file.

   Evidence: `tests/test_cc_complete.py` failed 3/7 under contention and passed **7/7** in isolation seconds later; `test_go_reconciliation_marks_completed` failed "on its own" in one run and passed alone in the next; across five consecutive runs of the lane-D subset, **every** non-pass was one of the two signatures above and none was a lane-D assertion. **Integration must run the suite with no other lane's pytest active**, or the numbers are noise. Longer term, `conftest.TEST_DATABASE` should be per-worker (e.g. `seldon-test-$PYTEST_XDIST_WORKER` or a PID suffix) — `tests/conftest.py` is not lane D's file.

3. **`_extract_description` was not uniformly broken.** As set out in §4, only the em-dash-H1 shape still reproduces; the other two named shapes are stale graph values from parsers that were already repaired. Reporting them as current parser bugs would have been wrong.

4. **The `seldon/ontology/` name collision.** §3(b). "Package location → `ontology/`" is ambiguous in this repo and the obvious reading resolves to the parser code package.

5. **`SELDON_ONTOLOGY_PATH` means two different things in two commands.** `seldon/commands/ontology.py::_resolve_vocabulary_paths` treats it as a single vocabulary **file** and raises "points to non-existent file". `seldon init` needs the ontology **root directory** for `shared_ontology.source`. One env var, two incompatible contracts. Lane D's side now diagnoses the mismatch explicitly (`NotADirectoryError` naming the difference) instead of writing a `<file>/<vocabulary>` path that can never exist. `ontology.py` is lane B's file — see §7.

6. **`seldon.yaml` in this repo is machine-specific and checked in.** Correcting the retired path was in scope; it still contains a legitimate absolute path (`/Users/brock/GitHub/seldon/ontology/`), which the D2 test deliberately permits while forbidding the retired root.

---

## 6. Deferred, and why

- **`scripts/launchd/com.brock.seldon-observability-dashboard.plist` and `scripts/launchd/install_dashboard_service.sh`** still hardcode `/Users/brock/Documents/GitHub/seldon`. Not in lane D's file set, and a launchd plist is an installed machine-local service definition where an absolute path is structurally required — the fix is for `install_dashboard_service.sh` to *generate* the plist from a derived root, which is a behaviour change to a live service. **Recommend a follow-up task.** They work today only through the same `Documents` symlink D2 is about.
- **Historical `Documents/GitHub` strings** in `CLAUDE.md`, `docs/**`, `cc_tasks/**` and `seldon_events.jsonl` were left alone — those are records, not defaults. (`/Users/brock/GitHub/seldon/CLAUDE.md` still states "**Seldon repo:** `/Users/brock/Documents/GitHub/seldon/`", which is now wrong; not a lane D file.)
- **Other hardcodes in `scripts/observability_collect.py`** (`DB_PATH`, `EXCLUDED_DBS`, `uri = "bolt://localhost:7687"`) were left as-is: out of D2's scope, and `bolt://localhost:7687` is duplicated in `init.py` and elsewhere, so it belongs in one config change, not a scattered one.
- **`_get_handoff_reconciliation` in `go.py` still has `except Exception: return None`** — a §4 "no lazy error handling" violation that predates this task. Changing it alters `seldon go`'s degradation behaviour on a graph outage, which is not a lane D defect and deserves its own decision. Flagged, not fixed.
- **`seldon verify` was not run and nothing was committed**, per instructions. No Seldon tasks were closed.

---

## 7. Cross-lane needs / integrator decisions

1. **`7120e000` and `676c0e39` cannot be re-derived.** Their source files no longer exist anywhere. Options: (a) accept the bad descriptions as historical, (b) set them by hand via an `update_artifact` event (`seldon artifact update`), (c) withdraw/supersede them using lane C's new terminal states — they are both `proposed` with no recoverable spec, which is arguably what `withdrawn` is for. Lane D took none of these; it is not lane D's call.
2. **37 of 49 registered CC tasks in `seldon-seldon-self` have missing source files**, and many carry metadata-shaped descriptions (`**Size:** XS`, `**Parent ResearchTask:** …`) that can never be re-derived. Same decision, at scale. Full inventory reproducible with the survey in §4.
3. **`seldon/domain/research.yaml` is uncommitted and currently red** (§5.1). Lane D cannot touch it. The 26-failure delta resolves when the lanes that consume it land.
4. **`seldon/commands/ontology.py` (lane B) and `seldon init` disagree on `SELDON_ONTOLOGY_PATH`** (§5.5). Recommend lane B accept a directory there too, resolving it against `DEFAULT_VOCABULARIES`, so one variable means one thing. `seldon.paths.DEFAULT_VOCABULARIES` / `ONTOLOGY_MARKER` are the constants to import.
5. **New module `seldon/paths.py`** is additive and referenced only by lane D's files, but it is outside the literal file list in the lane brief. It exists because both `init.py` and `go.py` needed the same derivation and `seldon/config.py` is not lane D's to edit. If the integrator prefers it in `config.py`, the move is mechanical.
6. **Run the full suite with no other pytest active** (§5.2) before recording the final count.
7. **`pyproject.toml` does not package `ontology/`.** If Seldon is ever shipped as a wheel, `seldon init` will now warn and omit the block (correct, loud) rather than emit a dead path — but shipping the vocabulary as package data would be the real fix. Not lane D's file.

---

## 8. Verification commands

```bash
# Lane-D-owned modules, in isolation (no other pytest running):
python -m dotenv -f .env run -- python -m pytest \
  tests/test_go.py tests/test_init.py tests/test_cc_utils.py \
  tests/test_cc_complete.py tests/test_cc_spec_hash.py \
  tests/test_cc_description.py tests/test_handoff_picker.py -v

# D1, live:
python -c "from seldon.commands.go import _find_latest_handoff; \
  print(_find_latest_handoff('/Users/brock/GitHub/ai-readiness-kg'))"

# D2, live:
python -c "from seldon.paths import resolve_ontology_source; print(resolve_ontology_source())"
grep -rn 'Documents/GitHub' seldon/ scripts/observability_collect.py \
  docs/templates/seldon_yaml_template.yaml seldon.yaml   # expect no hits

# D3, live:
seldon cc rederive-description <artifact_id|filepath> [--dry-run]
```
