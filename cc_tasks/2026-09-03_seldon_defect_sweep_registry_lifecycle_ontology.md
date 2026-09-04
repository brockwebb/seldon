# CC Task — Seldon defect sweep: Result registry contract, task lifecycle, ontology gaps, small defects

**Date:** 2026-09-03
**Project:** seldon (`/Users/brock/GitHub/seldon`)
**Authored by:** Desktop session
**Closes Seldon tasks:** `0bc41cfc`, `698d1d86`, `a3ba67a3`, `f951ed84`, `e3f751f6`, `1a23fd00`
**Spend:** zero model spend. No `claude -p` calls. No ceiling needed.
**SEQUENCING:** This task runs BEFORE `ai-readiness-kg/cc_tasks/2026-09-03_hygiene_sweep_post_g1_freeze.md`, which consumes the commands built here.

**Immutable once written. Changes require a new task file or an `_ADDENDUM-NN.md` sibling.**

---

## 0. Why one task

Six open Seldon tasks are defects surfaced by the same downstream project (ai-readiness-kg) in the same week. Four of them touch the same three modules (result registry, task state machine, ontology). Splitting them produces merge conflicts and four partial test runs. One task, four lanes, one integration pass.

Excluded on purpose (feature/design backlog, not defects): `7e862893`, `84c880a8`, `e911fc13`, `7120e000`, `59d67aeb`, `6dad25b9`, `63e151d5`, `369fc223`, `676c0e39`, `69494d5c`, `3454bf69`, `30746b6b`. Do not touch them except as noted in Lane D (description re-derivation).

## 1. Execution model — multi-agent

Run four lanes as subagents in parallel where file ownership is disjoint, then one integration pass. Each lane owns a file set; a lane must not edit files outside its set. If a lane discovers it needs a file another lane owns, it writes the need into its sub-RESULT and the integration pass reconciles. Lane ownership below is the conflict boundary — verify it against the actual module layout first; if the layout differs, redraw the boundary in the RESULT before starting and keep the disjointness property.

Each lane writes `cc_tasks/2026-09-03_seldon_defect_sweep_<lane>_SUBRESULT.md`. The integration pass writes the RESULT.

Before any lane starts: run the full test suite and record the baseline count (memory says 341; verify). All lanes end with their own tests green; integration ends with the whole suite green and count ≥ baseline + new tests.

## 2. Lane A — Result registry contract (`0bc41cfc`)

**Owns:** result registry module(s), `paper/build.py` resolver path (`resolve_references` and whatever renders `{{result:...}}` tokens), their tests.

### A1. `name` property
- `seldon result register --name NAME` (required for new registrations; not retroactively required on existing Results).
- Constraint: unique per project graph. Slug grammar: `^[a-z0-9][a-z0-9_.-]*$`, case-sensitive, ≤128 chars. Collision → hard error naming the existing Result's artifact_id.
- `{{result:NAME:value}}` resolves by `name` first. Design decision (Desktop, stated not asked): during a transition window the resolver falls back to matching `units` when no `name` matches AND the `units` string contains no whitespace-free unit token from the units vocabulary (see A2). Fallback emits a warning line per token so the fallback set is visible in build output. Remove the fallback in a later task; do not remove it here.

### A2. Migration of units-as-name Results — by event, never mutation
- Write `seldon result migrate-names [--dry-run] [--project-dir]`. For each Result with no `name`:
  - If `units` matches the units vocabulary (`%`, `rate`, `ratio`, `count`, `tokens`, `chars`, `seconds`, `minutes`, `docs`, `chunks`, `items`, `facts`, `USD`, `kappa`, and anything the codebase already treats as a unit — enumerate what you find and put the final vocabulary in `docs/conventions/`), leave `name` unset and record the Result in the dry-run report as `units_is_real_unit`.
  - Else emit a `result_name_assigned` event setting `name := units` and a `result_units_cleared` event (or one combined event if the event schema prefers) so `units` no longer carries the name. Record as `migrated`.
  - If a Result has `units` that both matches the vocabulary AND is used as a token key somewhere (the 14 ambiguous ai-readiness-kg cases per handoff) — record as `ambiguous`, do not assign, list in the report. The ai-readiness-kg task resolves these against its own resolver's behaviour.
- The command is run here only against seldon's own graph (if it has Results) and in `--dry-run` against ai-readiness-kg to produce the report; the live run on ai-readiness-kg happens in that project's task.

### A3. `--data-name` fails on unknown DataFile
- `seldon result register --data-name X` where no DataFile named X exists → hard error, exit non-zero, no event written. Same for `--script-name` if that flag exists.
- Add `seldon result backfill-provenance --map FILE [--dry-run]` where FILE is YAML/JSON `{result_name_or_id: {computed_from: [datafile names], generated_by: script name}}`. Emits `computed_from` / `generated_by` link events. Unknown names in the map → error for that row, continue others, report.

### A4. `--allow-proposed` render mode
- `seldon paper build --allow-proposed`: `resolve_references` no longer treats a `proposed` Result as fatal. Rendered form — Desktop decision: `<value> (proposed)` for markdown/plain targets, i.e. the resolved value followed by a single space and the literal `(proposed)`. For `verified`/`published` the render is unchanged. Build summary prints the count of proposed tokens rendered and the list of Result names. Default (flag absent) is unchanged: fatal, as today.
- Verify this decision against how `paper/build.py` actually renders tokens today (does it wrap values, format numbers, apply significant figures?). If the value formatting path makes `(proposed)` collide with something (e.g. a units suffix already appended), report the collision in the sub-RESULT and choose the least-surprising placement; state the choice. Do not ask.

### A5. Tests
- name uniqueness collision; slug rejection; resolve-by-name; fallback-by-units with warning; migrate-names classification of all three classes; `--data-name` unknown → error and no event; backfill-provenance dry-run and live; `--allow-proposed` render form and default-fatal preserved.

## 3. Lane B — Ontology gaps (`698d1d86` + item 4 of `0bc41cfc`)

**Owns:** master ontology vocabulary markdown under `ontology/`, `seldon ontology ingest/sync`, ontology tests.

- Add relationship types to the master `seldon-ontology`:
  - `corrects`: DesignNote→DesignNote, DesignNote→Result.
  - `annotates`: Issue→Result. `disputes`: Issue→Result.
  - `generated_by`: DataFile→Script. `computed_from`: DataFile→DataFile.
- `seldon ontology ingest` into master; `seldon ontology sync` on seldon's own replica. Do NOT sync into ai-readiness-kg here — that project's task does it.
- Tests: each new edge type accepted by the link validator with the stated endpoint types and rejected with wrong endpoint types (e.g. `corrects` Result→Result must reject unless you find a reason to admit it — if you admit it, say why in the sub-RESULT).

## 4. Lane C — ResearchTask lifecycle (`a3ba67a3` + `1a23fd00`)

**Owns:** task state machine module, `seldon task` CLI group, the MCP task tools (`seldon_task_close`, `seldon_task_update`, `seldon_task_list`), their tests.

### C1. Reconcile the `superseded` state that already exists
The ai-readiness-kg graph holds 30 ResearchTasks with `state = 'superseded'` while `a3ba67a3` claims no such state exists. Diagnose before designing: is `superseded` in the domain config's state list? Was it written by a code path that bypasses the state machine (paper sync? a bulk registrar?)? Query `USE \`seldon-ai-readiness-kg\``. Record the finding in the sub-RESULT. Then:

### C2. Terminal states
- Add `withdrawn` and `superseded` as terminal states reachable from `proposed`, `accepted`, `in_progress`. Both require `--reason`. `superseded` additionally takes `--superseded-by ARTIFACT_ID` (optional; validated if present) and writes a `superseded_by` edge.
- Not reachable from `completed`/`verified`. Nothing reachable from `withdrawn`/`superseded`.
- Existing rows already in `superseded` (C1) remain valid; if they lack a reason, that is a recorded finding, not something to backfill.

### C3. CLI/MCP parity
- Add `seldon task close <id> [--note]` with the identical state walk as MCP `seldon_task_close`. Add `seldon task withdraw <id> --reason` and `seldon task supersede <id> --reason [--superseded-by]`, plus MCP equivalents (or extend `seldon_task_update` to accept the new states with the reason argument — pick whichever matches the existing MCP tool pattern and state the choice).
- `seldon_task_list` / `seldon task list` exclude terminal states by default; `--all` includes them.

### C4. Claim marker (`1a23fd00`, minimal scope)
- On the `accepted → in_progress` transition record `claimed_by` (string: `desktop`, `cc`, or a caller-supplied agent id) and `claimed_at` (UTC). `seldon_task_list` and `seldon task list` surface both for `in_progress` tasks.
- Stale-claim expiry is a *report*, not an automatic transition: `seldon task list --stale-claims HOURS` lists `in_progress` tasks claimed longer than HOURS ago. No auto-release in this task.

### C5. Tests
- Every transition in the new matrix (allowed and forbidden); required reason; `superseded_by` edge creation and validation; CLI close walk equals MCP close walk (same event sequence); claim fields set and surfaced; stale-claim report.

## 5. Lane D — Small defects (`f951ed84`, `e3f751f6`, registrar description)

**Owns:** `seldon go` handoff picker, `seldon init` defaults, `seldon cc register` description parser, their tests.

### D1. Handoff picker (`f951ed84`)
- Diagnose (mtime vs name sort vs cached index). Fix: pick by the date prefix in the filename (`YYYY-MM-DD_`), tiebreak by mtime; if a file has no date prefix, mtime only. Test with two handoffs where name order and mtime order disagree.

### D2. `seldon init` shared-ontology default (`e3f751f6`)
- Derive from the installed package location (path of the seldon package → repo root → `ontology/`), not a hardcoded `/Users/brock/Documents/GitHub/...`. Test asserts no `Documents/GitHub` string appears in any default.

### D3. Registrar description parsing
- `seldon cc register` currently takes the wrong line as the task description for some files: seven ai-readiness-kg tasks have description `**Immutable once written. Changes require a new task file.**`; seldon tasks `7120e000` and `676c0e39` have truncated/boilerplate descriptions. Fix: description := first H1 text with a leading `# CC Task —`/`# Task —`/`# ` prefix stripped; if no H1, the first non-empty, non-bold-only, non-metadata line. Test on fixture files reproducing the three observed failure shapes.
- Add `seldon cc rederive-description <artifact_id|filepath>` that re-parses the file and emits a description-update event (never mutation). Run it on `7120e000` and `676c0e39` in seldon's graph. The seven ai-readiness-kg cases are handled in that project's task.

## 6. Integration pass

1. Merge lanes; resolve any cross-lane file needs recorded in sub-RESULTs.
2. Full test suite green; record final count vs baseline.
3. `seldon verify` on the seldon project itself clean (or every residual reported).
4. Reinstall/refresh the CLI so the new commands are on PATH for other projects (`pip install -e .` or whatever the repo's install path is — read the repo's own instructions; report which).
5. Close the six Seldon tasks with `seldon task close` (the new CLI — this is its first live use) with notes pointing at the RESULT. If `a3ba67a3`'s own close is blocked by anything, use the MCP tool and record the discrepancy.
6. `seldon cc complete` on this task file. Write the RESULT. Commit and push.

## 7. RESULT must report

- Baseline and final test counts.
- Per lane: what shipped, what was deferred and why, any premise in this file that live state contradicted (report, never reconcile silently).
- C1 finding: where the 30 `superseded` rows came from.
- A2 dry-run report against ai-readiness-kg: counts of `migrated` / `units_is_real_unit` / `ambiguous`, with the ambiguous list in full.
- A4: the chosen render placement and why, if it differs from `<value> (proposed)`.
- The install/refresh mechanism used in §6 step 4.
- Confirmation that `docs/design_decisions.md` or the seldon equivalent received an appended, dated entry for: name-as-token-key with transitional units fallback; `(proposed)` render form; terminal-state semantics; claim marker semantics. Append only.
