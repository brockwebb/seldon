# RESULT: SEL-009, `models refresh` does not move the lock while a run holds it, and the pilot is sized to what it detects

**Date:** 2026-10-24
**Session:** interactive Claude Code session (operator-launched, not dispatched), branch `worktree-SEL-009` in
`.claude/worktrees/SEL-009`. Task 30c0de2c.
**Addenda:** `cc_tasks/*SEL-009*ADDENDUM*.md` globbed, two read before any work:
`2026-10-24_SEL-009_ADDENDUM_00_ad035_r7_already_rules_it.md` (Part A is R7 conformance) and
`2026-10-24_SEL-009_ADDENDUM_01_squiddy_r232_landed.md` (R-232 is the consumer's half; do not duplicate it).
**Model calls:** zero. Every refresh in the tests runs the fake CLI and fake npm of `tests/test_models.py`.

## Premises, as checked at start

All five held, each with exit 0, run from the primary checkout before the worktree was cut:

- `grep -q 2026-10-24T00:09 models/models.lock.yaml` (`resolved_at: '2026-10-24T00:09:23.634936Z'`).
- `grep -q cli_not_piloted .../hazbrief-mcp/cc_tasks/2026-10-23_HB-24_..._RESULT.md`.
- `grep -q 4,212,332 .../hazbrief-mcp/cc_tasks/2026-10-24_HB-25_..._RESULT.md`.
- The two SEL-008 premises the parent checked in the same pass (not this task's).

**One premise in the task's prose was false:** "hazbrief's rating top-up was mid-run under a dispatcher lease".
hazbrief-mcp's `seldon.yaml` has no `dispatch:` block, its ledger has no `dispatch_launched` line, and HB-24's
RESULT names its executor as "Claude Code (Opus 5.5), session hazbrief-mcp-8b": an interactive session. That moves
the fix. A check of dispatcher leases alone, which is what Part A step 1 asks for, would not have stopped this bump.

## Governing decisions, and the prior art this implements

- **AD-035-R7**, quoted in full (`docs/design/AD-035_config_driven_model_selection.md:69-71`, register record 00220):

  > ## AD-035-R7. Change only at a boundary
  >
  > A run in flight keeps its lock entry to the end. A gated or sealed instrument re-pilots on a bump, per H-006 R-30. Sealed records keep the ids they were made with. Those are history, not staleness.

- **AD-035-R2**: the refresh "runs when a task is authored and when a run starts; the result is cached for the day".
  R14 amends its day.
- **AD-038-R1**: the dispatcher's reconciler commits store lines, whoever wrote them. So the deferral line is
  appended and not committed by the refresh.
- squiddy **R-232** (SQ-038R, 7322bc7): a run holds the binary it was piloted on. Not duplicated (ADDENDUM-01).
- The new rulings are in `docs/design/AD-035_ADDENDUM_03_a_run_holds_the_lock_and_a_project_declares_its_pilot.md`:
  **AD-035-R13** (the refresh defers while a run holds the lock), **R14** (the day boundary is one printed value) and
  **R15** (a project's tiered-pilot declaration). Prior art, with what each source decided:
  - flock(1): a run hold is an flock taken for the command's life;
  - Renovate's schedule and Dependabot's windows: the boundary is configuration, and there is no bump under a holder;
  - ITIL change freezes: a recorded override (`--force`, `forced_over_holders`);
  - ISO 2859-1 switching rules: the pilot tiers;
  - ISO/IEC 17025 6.4.10 against 7.2.2.2: an intermediate check against a re-validation, as squiddy SQ-062 cites it.

  The library arm returned nothing on point. Internal receipts find R7 itself, squiddy's R-232 note, and nothing for
  the mechanism's own words.

## Part A: why R7 was not honoured on 2026-10-24 (ADDENDUM-00 step 2)

ADDENDUM-00 named three possible causes. Each one is answered from the code:

1. **`models refresh` keeps no per-run entry, and had no notion of a run.** `refresh()` checked the day cache, then
   the branch, then went straight to npm and the probes:

   ```python
   if (old and not force and cfg["cache"] == "day" and str(old.get("resolved_on")) == today ...):
       return RefreshOutcome(status="cached", ...)
   if commit and old is not None:
       why = _cannot_commit(_repo_root(home), cfg["commit_branch"])
       ...
   pkg = cfg["npm_package"]
   if version is None:
       res = npm(["npm", "view", pkg, "version"], ...)
   ```

   The lock holds one head (`cli:`, `families:`), not an entry per run. **Seldon's defect: fixed here (R13).**
2. **The run never registered itself against the lock.** No mechanism existed to register, so hazbrief could not have.
   The dispatcher honours R7 for its own launches only: it refreshes before a launch and carries the spec in the
   lease (`seldon/commands/dispatch.py`, the comment "AD-035 R2 and R7: ... this run keeps the spec it starts with").
   hazbrief has no dispatcher. **This is now the consumer's to adopt**, so it is filed as hazbrief
   `cc_tasks/2026-10-24_HB-31_long_runs_hold_the_model_lock.md` (task `ed287bf0`, proposed): long runs go under
   `seldon models hold`.
3. **squiddy's `pin_cli` read only the lock head.** Before R-232 (`git show 86d11aa^:squiddy/extract_daemon.py`, line 1114):

   ```python
   lock_path, lock_ver = client.executable, str(getattr(client, "lock_cli_version", "") or "")
   ...
   if want_ver is not None and str(want_ver) != lock_ver:
       diffs.append(f"transport.cli_version declares {want_ver}, the lock's CLI is {lock_ver}")
   if diffs:
       raise SystemExit(f"FATAL: cli_not_piloted: ...")
   ```

   R-232 fixed this on squiddy's side and it is not duplicated. No squiddy stub is filed for it.

**The trigger:** seldon's ledger has `models_lock_bumped` at 00:09:23Z. hazbrief's ledger has `artifact_created`
by `desktop` (task `17cc0b1e`) at 00:09:26Z. So it was a Desktop registration's `ensure_fresh("register")`
(`seldon/commands/cc.py:1253`), the first trigger after 00:00Z. There is no clock: the "about 00:49Z" the operator
planned around was the time of the previous day's first trigger. **`prune.repositories` lists no hazbrief-mcp**
(`[., ../squiddy, ../arnold, ../ai-readiness-kg]`), so the task's suggested holder source would have missed hazbrief
even if it had a dispatcher. The holder list is a new `refresh.holders` in `models/registry.yaml`.

### What was built (Part A steps 1 and 2)

- `seldon/models.py`:
  - `lock_holders()` returns every live holder:
    - a dispatcher lease (`lease_is_held`, DD-022 PID liveness) in each `refresh.holders` repository;
    - a worktree lease (`worktree_holder_alive`) in the same repositories;
    - a run hold (flock held) under `refresh.holds_dir`.

    A lease naming the calling process is excluded. In serial mode the dispatcher refreshes at a launch while
    holding its own pass lease. In worktree mode `_start_claimed` calls `ensure_fresh("dispatch")` before it writes
    the launching task's worktree lease, so that lease never counts. The list resolves against the seldon PRIMARY
    checkout (`_primary_root`, `git rev-parse --git-common-dir`), so a worktree reads the same siblings. A listed
    directory that does not exist raises `ModelsError` naming it, and the lock stands (`ensure_fresh` turns it into
    a warning). A repository with no `dispatch:` block holds nothing. `seldon.core.dispatch` is imported lazily, so
    `import seldon.models` stays cheap for other repositories.
  - `hold(run, by)`: a context manager that takes an flock on `<holds_dir>/<run>.lock`. Its body is
    `{run, by, pid, lock_cli_version, acquired_at}`, and the release is recorded in place. A run name must be one
    path segment, and a second hold of the same name is refused.
  - `refresh()`: when a lock exists and a holder is live, there is no npm call, no probe and no lock write. It
    appends one `lock_refresh_deferred` event (cache day, holders, the lock's CLI version) unless the last deferral
    had the same day and holder set, and returns status `deferred`. The line is not committed (AD-038-R1). `--force`
    refreshes anyway and adds `forced_over_holders` to the `models_lock_bumped` payload. A holder list that cannot be
    read does not block an operator's `--force`. A first refresh, with no lock, is never deferred.
  - `cache_day()` and `next_refresh_at()`: the cache day is the date of now minus `refresh.cache_boundary_utc`,
    validated as `HH:MM` at load.
- `seldon/commands/models.py`:
  - `seldon models hold --run NAME [--by X] -- CMD ...` runs CMD under the hold and exits with its code.
  - `refresh` prints the holders on a deferral and exits 0.
  - `show` prints the boundary, the next eligible instant, the triggers ("no clock job runs it") and the holders.
- `models/registry.yaml`:
  - `cache_boundary_utc: "00:00"` (today's behaviour);
  - `holders: [., ../squiddy, ../ai-readiness-kg, ../arnold, ../hazbrief-mcp]`. The first three have `dispatch:`
    blocks. arnold and hazbrief have none today and hold nothing until they do. No other sibling under `~/GitHub`
    has one; all were checked;
  - `holds_dir: ~/.local/share/seldon/model-holds`.

  `tests/models_fixture.py` sets `holders: []` and a temporary `holds_dir`, so no test reads the machine's real leases.

Live, read-only, from the worktree: `seldon models show` printed
`refresh: day boundary 00:00Z; next eligible 2026-10-25T00:00:00Z; it runs at the first `seldon cc register` or
`dispatcher launch` after that instant with no run holding the lock (no clock job runs it)` and `holders: none`.

## Part B: the declaration and its contract

`seldon.yaml` of the project that pilots:

```yaml
models:
  pilot:
    cost_calls: 50        # int >= 1
    cost_band: 1.5        # number > 1; required when full_on names band_tripped
    content_sample: 75    # int >= 1
    full_on: [major, band_tripped]   # any of major, minor, band_tripped
```

`seldon.models.pilot_declaration(project_dir)` returns the mapping, or None when it is absent. It raises `ModelsError`
naming the key on an unknown key (under `models:` or `models.pilot`), a missing required key, a bool or non-integer
count, a band of 1 or less, or a `full_on` that is not a list drawn from the three values.
`seldon models show [--project DIR]` (default: the current directory, when it holds a `seldon.yaml`) prints it. It is
not in the lock, because the lock is written only by `refresh`.

**The contract a reader implements** (squiddy `pin_cli` / `squiddy pilot`; Seldon validates and decides nothing):

| key | meaning |
|---|---|
| `cost_calls` | the first N calls on the new CLI are read against the recorded pilot's weighted cost per call |
| `cost_band` | tripped when that ratio, new over recorded, is above it or below its inverse. hazbrief's HB-29 band is 0.67x to 1.5x, i.e. 1.5 here |
| `content_sample` | that many recorded units are re-run on the new CLI and compared on content (squiddy's `equivalence_tolerance`) |
| `full_on: major` | the full pilot when X differs in the CLI version X.Y.Z |
| `full_on: minor` | the full pilot when X or Y differs |
| `full_on: band_tripped` | the full pilot when the cost band trips |
| (always) | a failed content comparison escalates to the full pilot; the cost line is recorded on every requalification (SQ-038R ADDENDUM-00 section 4: the cost moved 2x while content moved by at most one claim) |

No declaration means today's behaviour: the whole recorded pilot. On 2026-10-24's numbers (SQ-038R ADDENDUM-00
section 2), a band of 1.5 would have tripped on the first document that made calls: `bts-ntad-rail-lines-layer`,
6,560 against 1,439 weighted per call. The pooled figure was 1,843 against 926 (ratio 1.99). With `band_tripped` in
`full_on`, the full pilot is still owed. Without it, the cost line is recorded and the content sample decides, on a
tenth of the 733 same-text claims. The task's "1,439 against 926" pairs the first document's 2.1.309 rate with the
pooled 2.1.309 rate, so this RESULT does not use it.

**Squiddy stub:** `../squiddy/cc_tasks/2026-10-24_SQ-088_pin_cli_and_squiddy_pilot_read_the_projects_tiered_pilot_declaration.md`
cites SEL-009, SQ-038R, R-232 (c), SQ-062 and SQ-086. It was registered with
`seldon cc register --project /Users/brock/GitHub/squiddy --allow-untracked <file>` as task `d7c72532` and committed
by its registration (squiddy 41eda58). Two refusals came first, both fixed in the file: `parts_undeclared` (no
`**Parts:**`), then a Parts entry that did not parse. The registration's event lines were left uncommitted:
squiddy's store was dirty with its standing dispatcher's lines, so it skipped them with reason
`store_dirty_before_registration`, and that dispatcher reconciles them (AD-038-R1). Not pushed by this session; on origin/main as of the merge (pushed by that repository's own sessions).

**hazbrief stub:** `../hazbrief-mcp/cc_tasks/2026-10-24_HB-31_long_runs_hold_the_model_lock.md`, task `ed287bf0`. The
registration's own commit lost a ref race with HB-30's record commit:
`fatal: cannot lock ref 'HEAD': is at 68475a18... but expected 61b975bc...`. hazbrief has no dispatcher to pick the file
up, so it was committed path-scoped by hand, and the one registration line after it. Not pushed by this session; on origin/main as of the merge (pushed by that repository's own sessions).

## Tests, red then green

`tests/test_sel009_refresh_defers_and_pilot_declaration.py`, 27 tests, written before any change to `seldon/`:

- **Red, on base 20f9c8e:** 24 failed and 3 passed (`docs/evidence/sel009/red_run_on_base_20f9c8e.txt`). The three
  that passed are the negative controls: the caller's own lease, a released lease or dead PID, and a repository with no
  `dispatch:` block. Each asserts that the refresh bumps exactly as before.
- **Green:** 27 passed.
- **Covered:**
  - a held global lease defers: the lock bytes are unchanged, no npm or CLI call is made, one deferral line is
    written, and the same day writes no second line;
  - a live worktree lease defers;
  - the caller's own-PID lease is ignored, and a released or dead lease holds nothing;
  - a repository with no dispatch block holds nothing;
  - a missing holder directory raises `ModelsError` and the lock stands;
  - a run hold defers and releases afterwards, and a bad run name is refused;
  - `seldon models hold -- cmd` holds while cmd runs and exits with its code;
  - `--force` records `forced_over_holders`;
  - no holders refreshes as before;
  - a first refresh is never deferred;
  - the boundary keying;
  - a malformed boundary is refused at load;
  - `show` prints the boundary, the next refresh and the holders;
  - the declaration: valid, absent and nine malformed cases, plus a band without `band_tripped`.

Targeted runs, `PYTHONPATH=<worktree> python -m dotenv -f /Users/brock/GitHub/seldon/.env run -- python -m pytest ...`:

- `tests/test_models.py tests/test_models_catalog.py tests/test_models_checker.py tests/test_no_live_model_calls.py
  tests/test_qc_calibrate_judge.py tests/test_sel009_refresh_defers_and_pilot_declaration.py`: **95 passed** (77 s).
- The dispatch test files that import `seldon.models` (`test_dispatch*.py`, `test_friction002_worktree_only.py`,
  `test_cadence_pass.py`, `test_audit_dispatch.py`) use the shared Neo4j test database and were left to the full-suite
  gate, by agreement with the parallel SEL-008 work.

**Full-suite gate** (combined SEL-008 + SEL-009 tree, merge c434836, run once because the suite's Neo4j tier and the two branches overlap in `tests/models_fixture.py` consumers): `PYTHONPATH=<worktree> python -m dotenv -f .env run -- python -m pytest tests/ -q`: **2870 passed, 7 skipped, 2 failed** in 38 min 22 s. (1) `tests/test_verify_event_log.py::test_all_checks_include_the_two_new_ones` pinned 18 checks; SEL-008 adds the 19th ("Blocks and waits"), so the test now pins 19 and names it (14 passed after). (2) `tests/test_pa002_release_resolve.py::test_rebuilding_the_served_release_reproduces_the_served_index` fails identically on unmodified main (run on main 20f9c8e: 1 failed): `release_unavailable ... the index: block of squiddy/graphs/library/extract/control.yaml at edd5d5d66bf differs from today's`. It is the squiddy library's index drift, the same cause as SEL-009's stale AD-035 receipts; not this change's, filed as an Issue (see After the merge).

## Decision records and the prior-art verdict

- Pending records, written by `seldon decision accept --decided-by cc:30c0de2c`, to be numbered on main after the
  merge (`seldon decision number`):
  - `docs/decisions/register/pending/00001_03ee92a13f300e3b_seldon-ad-035-r13_accept.yaml`
  - `docs/decisions/register/pending/00002_4fabcbc4b3d9d220_seldon-ad-035-r14_accept.yaml`
  - `docs/decisions/register/pending/00003_c8d0ec6cd3fc50ca_seldon-ad-035-r15_accept.yaml`
- `seldon prior-art verify docs/design/AD-035_ADDENDUM_03_...md`: **every receipt in ADDENDUM 03 passes** (one
  library, six internal). The verdict is **FAIL**, recorded in the governed ledger as event
  `338e88ee39b5448e91b310c5608e5883`. The verify takes the whole AD-035 family, and three library receipts in the
  EARLIER addenda are `release_unavailable`: `AD-035_ADDENDUM_01_prior_art_verified.md:30` and `:31`, and
  `AD-035_ADDENDUM_02_pinned_roles.md:54`. The reason given is "the `index:` block of
  squiddy/graphs/library/extract/control.yaml at c40f79ccd445 [a34b25cf5283] differs from today's". This existed
  before SEL-009: no edit to ADDENDUM 03 can change it, because a committed note is immutable (AD-036-R7). It is the
  index-rule drift that SEL-009 ADDENDUM-00 already recorded as "not this task's". **Correction (by the merging
  session):** it holds no task. Addenda are exempt from the gate (`seldon.yaml` `prior_art.exempt_globs:
  ['*_ADDENDUM_*.md', ...]`) and `governing_notes` resolves `AD-035` to the base note only, whose verdict is unchanged;
  `check_prior_art` on the merged tree passes (3 notes outside the baseline, each passing), as on main. The FAIL verdict
  is a record, not a hold.

## Not done, and why

- **The full suite was not run here.** It shares one Neo4j test database with the SEL-008 work running in parallel,
  and the parent runs it once on the combined branch.
- **No merge, no push, no `cc complete`**, by the dispatching instruction.
- **squiddy's reader of R15** is SQ-088's work, and **hazbrief's adoption of `seldon models hold`** is HB-31's.
  Seldon writes nothing in either repository's code.
- **A busy parallel dispatcher can defer the refresh all day.** That is R7's price, and it is recorded rather than
  hidden: every deferral is a ledger line naming who held the lock, and `--force` is the operator's override.
- **The AD-035 family's stale library receipts** (above) need a library index rebuild or fresh receipts in a new
  addendum. Neither is in this task's scope.
