# SEL-029 RESULT: a receipt against a release the library no longer carries verifies against one it does; the verdict ledger commits beside its note; an addendum with a candidacy header is refused. The register never carried `7b72aaa89fe005d3`: nothing dropped the row, because none was written.

**Task:** `c09de1a7`. **Executed:** Claude Code (Opus 5.5), worktree `witty-meandering-rivest` (branch
`worktree-witty-meandering-rivest`), 2026-11-08, headless, on base `04ac6cc`.
**Addenda:** none. I listed `cc_tasks/` for `SEL-029` addenda and found none.
**Not done, per the dispatcher's launch instructions:** merge, push and `seldon cc complete`.
**Network:** none beyond git. **Model calls:** zero. **Tokens at the last Part boundary:** 235,389 (estimate 0.6M).

Recall used: none

(The listed hits cover the return mechanism (SEL-023), registration commits (SEL-006, DESK-001) and worktree anchoring
(HOOK-002). I did not open them this session. What I needed from them was already in this machine's session memory:
the DESK-002 register exception, the `cc return` route and the worktree verify crash.)

## The register finding (step 1), stated plainly

**`7b72aaa89fe005d3` was never a row of squiddy's `EXPORT_VERSIONS.md`. Nothing removed it.** That is neither of
SEL-028's two hypotheses. It is a third case: squiddy served an index bound to a release that was never sealed.

- `git -C ../squiddy log -S'7b72aaa89fe005d3' --all -- graphs/library/exports/EXPORT_VERSIONS.md` finds no commit.
  `-G'sq114_a'` finds one, `a8f2266c` (2026-11-06 21:14). It adds the `20261105_sq114_a.r1` row, sha `79e52df405ff4536`.
- The export with digest `7b72aaa8...` is on disk twice, as `library_graph_20261105_sq114_a_2026-11-05.json` and
  `..._2026-11-06.json`.
- SQ-114 (2026-11-05) wrote that export at stage 13 and halted at stage 15 `conformance`. SQ-114R then rebuilt the served
  index over the export (stage 15 `index`: pass) and halted at `index-parity`. Stages 16 to 18 (`registers`, `seal`)
  never ran: "Nothing was appended to `EXPORT_VERSIONS.md`" (squiddy SQ-114R RESULT, stage table). From then until
  `20261106_sq125_c` was sealed, `search` reported release `7b72...`, and DN-019's receipt was taken in that window.
- The defect is in squiddy's release steps: the `index` stage serves a release before the seal registers it. I filed it
  into squiddy as a `**Kind:** filing`:
  `cc_tasks/2026-11-08_the_library_s_served_index_carried_release_7b72aaa89fe005d3_for_about.md` (task `c923eb5a`,
  squiddy commit `ee7ae97e`). Part A went ahead anyway, as the task says: verify may not assume a register that keeps
  every row.

## Part A: a superseded release verifies (AD-036-R19)

- `seldon/core/prior_art.py`: when `search_release` fails, `_resolve_superseded` asks `Library.resolve_superseded` for a
  carried release that holds every row the receipt lists. It tries the served release first (its index database's rows,
  after hashing the database against `index_manifest.json`). It then tries up to `prior_art.library.superseded_releases`
  register releases, newest first. Each of those needs its export on disk hashing to the register's 16 hex, and its rows
  come from `release_row_ids`, which is steps 1 and 2 of `rebuild_release`. Those steps are now shared through
  `_release_rows`.
- If a release holds every row, the status is `pass (superseded)` (`SUPERSEDED`, a status that does not fail the note).
  The receipt gets `verified_against: {release, sha256}`, and its detail names that release and why the named release
  failed. The note is not rewritten. The verdict payload, and so the ledger, carries the resolution.
- If none does, the status stays `release_unavailable`. The detail adds `rows missing from the current release <name>:
  ...` and `not checked: ...` for any carried release that could not be read. A `rows none` receipt is never resolved
  this way.
- **Row ids are matched whole.** The task said "up to the release-specific suffix the index rule defines". squiddy's
  rule `sq028r-index/3` defines no such suffix. A row id is `<doc id>#<pointer into the text>` or `<doc id>#meta`, with
  nothing that names a release. I recorded that instead of inventing a suffix (AD-036 ADDENDUM 11 §2). A test pins it:
  a moved pointer does not match.
- **Configuration:** `superseded_releases: 3` is set explicitly in `seldon.yaml`, and the code default is the named
  constant `SUPERSEDED_RELEASES_DEFAULT`. The bound exists because each register release costs one pass over a 0.6 GB
  corpus checkpoint.
- **Live measurement (2026-11-08):** all 45 rows of DN-019's base receipt are in the served `20261106_sq125_c` database.
  With this branch, `verify_note` on DN-019 and its ADDENDUM-01 returns **PASS**. Line 62 resolves `pass (superseded)`
  against `library_graph_20261106_sq125_c_2026-11-06.json`, and the addendum's receipt passes outright. The script
  `/tmp/sel029/live_dn019.py` turned the query log off and recorded no verdict, so it wrote nothing to hazbrief-mcp.
  hazbrief-mcp's three dirty files (`seldon_events.jsonl`, `state/prior_art_queries.jsonl`,
  `state/prior_art_verdicts.jsonl`) predate the run. The newest query line is 17:48Z, from its own FAIL run.
- **Tests** (`tests/test_sel029_superseded_release.py`, 9):
  - a removed release passes superseded when the served release holds its rows;
  - one absent row fails, and that row is named;
  - matching uses the full row id;
  - a register release is consulted newest first, and the search stops at the first hit;
  - `superseded_releases: 0` consults only the served release;
  - a carried export whose bytes moved is skipped and named;
  - a `rows none` receipt is not resolved;
  - the register is parsed in the kit's row format;
  - the database rows are read.

  The existing `release_unavailable` tests are unchanged, including the unreadable root and the unreadable commit
  (internal arm). The stub in `tests/test_prior_art.py` gained a `resolve_superseded` that carries nothing.
- `TOOL_VERSION` stays `prior-art/1`: the served path, ranking and matching are unchanged (ADDENDUM 11 §4.3).

## Part B: the ledger commits beside its note (AD-036-R20)

- `seldon/core/desktop_commit.py`: the ledger is `prior_art.verdict_ledger`, which is the governed ledger or
  `gate.verdict_ledger_without_governed`, so hazbrief-mcp's is `state/prior_art_verdicts.jsonl`. It is accepted in a
  call naming a design note or addendum whose current bytes have a verdict in it. An addendum counts when a verdict's
  `addenda` list carries its path and sha. Alone, or beside files it holds no verdict for, it refuses `outside_roots`,
  naming the rule. The message leaves the ledger out (`desktop: design: AD-099_x.md`). This mirrors DESK-002's
  register exception.
- **Step 6, what was ruled:** no. The gate does not read a verdict from an unstaged ledger. The staged ledger is the
  proof (HOOK-001): a verdict read from disk would admit a commit that does not hold its own proof, and the tool can now
  stage the ledger. Recorded as AD-036-R20, and pinned by
  `test_without_the_ledger_the_hook_still_refuses_and_says_to_stage_it`.
- **Tests** (`tests/test_sel029_ledger_and_addendum_commit.py`, Part B, 6):
  - the ledger beside its note commits in one commit with the right message;
  - without the ledger the hook still refuses;
  - the ledger alone refuses and stages nothing;
  - the ledger beside a note edited after its verdict refuses;
  - the ledger beside an addendum its verdict carries commits;
  - the CLI `seldon commit-governed` and the MCP tool body (`__wrapped__`) refuse and commit through the same path.

  These sit in a new file beside the DESK-002 tests rather than inside `test_desk002_ruling_commits_with_record.py`.
  They use the same `repo` fixture and the same real hooks; keeping them separate leaves the DESK-002 file unchanged.

## Part C: an addendum cannot carry Spend (AD-038-R24)

- `seldon/core/dispatch.py`: `ADDENDUM_FORBIDDEN_HEADERS` (`Spend`, `Network`, `Framework layer served`, `Exclusive`),
  `is_addendum_name` and `addendum_header_refusal`. The check reads the whole addendum, outside fenced code and code
  spans. It refuses `addendum_carries_header: **<header>:**; headers are read from the task file only (AD-038-R11); to
  change one, re-file the task with an R suffix`.
- It runs at `seldon_commit_governed` / `seldon commit-governed` (`desktop_commit._addendum_refusal`, before anything is
  staged) and at `seldon_cc_register` / `seldon cc register` (`register_task_file`, before anything is written). Both
  register surfaces print the line as is, without the generic "cite the AD or DN" fix line.
- **What this does not catch:** HB-115's real addendum wrote the raise in prose ("Spend rises to 1200000 for the Part 0
  work.", hazbrief-mcp `..._ADDENDUM_01_...md:33`), not as a `**Spend:**` header. No header check sees that. The refusal
  catches the header form, and the ruling text and the MCP tool's docstring state the rule.
- **Step 9:** the wait form is Issue `0555aa72` on seldon ("SEL-027 wait form: a Part that waits on an operator input
  without spending its ceiling"). It carries SEL-027's text and is open for a design note.
- **Tests** (Part C, 9):
  - each of the four headers is named;
  - a header in a code span or fence is prose;
  - an addendum with a Spend line is refused at commit-governed (core and MCP), with nothing staged;
  - an addendum without one commits as before;
  - name recognition;
  - an addendum with a Spend line is refused at `seldon_cc_register` (MCP body) and at `seldon cc register` (CLI), on
    real Neo4j.

  No existing addendum marker test was touched; `SUPERSEDED_MARKER` and `MARKER_WINDOW_LINES` are unchanged.

## Rulings and records

- `docs/design/AD-036_ADDENDUM_11_a_superseded_release_verifies_and_the_ledger_commits_with_its_note.md`: AD-036-R19
  and R20, with the register evidence and the prior art. External: Memento RFC 7089, RFC 5829 version links, in-toto and
  Sigstore bundles. Internal: ADDENDUM 06, DESK-002, HOOK-001.
- `docs/design/AD-038_ADDENDUM_10_an_addendum_cannot_carry_a_candidacy_header.md`: AD-038-R24. Prior art: Kubernetes
  immutable-field validation, RFC 5322 §2.1, AD-038-R11/R14.
- Register records, written by `seldon decision accept --from` and so un-numbered in the worktree; the merge numbers
  them:
  - `docs/decisions/register/pending/00001_..._seldon-ad-036-r19_accept.yaml`
  - `docs/decisions/register/pending/00002_..._seldon-ad-036-r20_accept.yaml`
  - `docs/decisions/register/pending/00003_..._seldon-ad-038-r24_accept.yaml`
- I cited the external sources by their published names and did not fetch them, because the Network header allows only
  git.

## SEL-028's and SEL-026's other questions, answered

- **Should a stale base receipt block an addendum whose own receipts pass?** It still fails the verification:
  `verify_note` judges a note together with its addenda (`prior_art.addenda_of`). R19 removes the cause instead of
  splitting the judgment.
- **Why did the gate accept the addendum after a FAIL?** Addenda are exempt from the commit gate
  (`prior_art.gate.exempt_globs`: "verified WITH [the note], so they are not gated alone"). An addendum commit never
  consults a verdict, so committing it was by design.
- **Is `seldon_cc_file` exposed?** Yes, since `433fdb9` (SEL-023, 2026-11-06 08:24). A Desktop whose `seldon-mcp`
  process started before that has the older tool list until the server restarts.

## Gate

- **Full suite** (`python -m dotenv -f .env run -- python -m pytest tests/ -q -n 6`, 55 min): **3262 passed, 5 failed,
  7 skipped.** None of the 5 is this branch's:
  - `test_pa002_release_resolve::test_rebuilding_the_served_release_reproduces_the_served_index`: the known library
    index drift, which fails on main. It ran through the refactored `rebuild_release` and reached its fingerprint
    comparison.
  - Three `test_dispatch_parallel` timing tests (`test_two_disjoint...`, `test_an_exclusive_task_waits...`,
    `test_a_killed_supervisor...`): all three **pass** re-run alone.
  - `test_sel024_gate_record::test_fixture_a_regate_whose_gate_outlasts_lock_wait...` asserts that a filing finishes
    inside a 6 s gate sleep. It failed alone too, with load averages of 12 to 25 from other sessions. **Main's code
    (`04ac6cc`, a `/tmp` shared clone) fails it identically under the same load**, so it is load, not this change.
- The 24 SEL-029 tests and the prior-art suites (`test_prior_art*`, `test_pa002` except the drift test,
  `test_disp003_self_citation`) pass.
- **`seldon verify`:** it crashes in this worktree in `check_decisions` (`KeyError: 'record_hash'`). That is the known
  crash on un-numbered pending records, and the merge numbers them. I ran every other check directly
  (`/tmp/sel029/verify_checks.py`): 16 pass, and `File hashes` and `Governed docs` fail. The same script on the primary
  checkout fails the same two, plus `Commit hook`, so this branch adds no verify failure. The `File hashes` failures
  are `2026-09-15_standing_dispatcher.md` and `AD-036_ADDENDUM_01_self_test.md`, neither touched here. The
  `Governed docs` failures are uncataloged cc_tasks from October.
- **Parts:** `part-complete` recorded A, B and C (no stop).

## Commits on this branch

- `441cd93`: Part A, AD-036 ADDENDUM 11, records R19 and R20.
- `aee07f8`: Parts B and C, AD-038 ADDENDUM 10, record R24, Issue `0555aa72`'s event line.
- This RESULT.

## Returns

I ran `seldon cc return <this task> --answers seldon:SEL-028` after a `--dry-run`. It wrote
`hazbrief-mcp/cc_tasks/2026-11-08_HB-138_sel_029_answered_sel_026_sel_027_and_sel_028_re_verify_dn_019_commit_v.md`
from the `## For hazbrief-mcp` section below and registered it there as task `da4c3253`. hazbrief-mcp commits
`3f8e20ac` and `4e23b49a` record it. The return names the Part and the tests for each of the three filings.

The returns machinery keys a return by the answering task, so one task files one return. The two later runs
(`--answers seldon:SEL-026`, then `seldon:SEL-027`) found HB-138 ("return already filed") and closed each filing
against it. `seldon task show` now reads `completed` for SEL-026 `9f0c7e1b`, SEL-027 `6e5d0d94` and SEL-028
`771032cd`. The closing events are in this branch's `seldon_events.jsonl`.

The task's step 1 also asked for a filing into squiddy: `c923eb5a`, squiddy commit `ee7ae97e`, above.

## For hazbrief-mcp

**Title:** SEL-029 answered SEL-026, SEL-027 and SEL-028: re-verify DN-019, commit verified notes with their ledger, and re-file a Spend raise

seldon's SEL-029 (task `c09de1a7`) landed one answer for each of the three filings hazbrief-mcp filed into seldon.

1. **SEL-028 (Part A, AD-036-R19).** A library receipt whose release cannot be rebuilt now verifies as
   `pass (superseded)` when the current release (or a recent register release) holds every row it lists, and the
   verdict names that release. DN-019's base receipt (release `7b72aaa89fe005d3`) has all 45 of its rows in
   `20261106_sq125_c`. Measured with seldon's branch code, DN-019 with its ADDENDUM-01 verifies PASS. Squiddy's
   register never carried `7b72...`: SQ-114R served the index over an export that was never sealed. That is filed into
   squiddy (`c923eb5a`). Tests: `tests/test_sel029_superseded_release.py`.
2. **SEL-026 (Part B, AD-036-R20).** `seldon_commit_governed` now accepts `state/prior_art_verdicts.jsonl` in the same
   call as the note or addendum whose current bytes it holds a verdict for. The ledger alone still refuses, and the
   gate does not read the ledger from disk. `seldon_cc_file` has been exposed since seldon `433fdb9` (2026-11-06); if a
   Desktop does not list it, restart its `seldon-mcp`. Tests: `tests/test_sel029_ledger_and_addendum_commit.py`.
3. **SEL-027 (Part C, AD-038-R24).** An addendum may not raise Spend. Candidacy headers are read from the task file
   only, so a raise is a re-filing with an R suffix. An addendum carrying `**Spend:**`, `**Network:**`,
   `**Framework layer served:**` or `**Exclusive:**` is now refused at `seldon_commit_governed` and
   `seldon_cc_register`, with that line. A raise written in prose is not caught, so do not write one. The wait form is
   open as seldon Issue `0555aa72`. Until it is designed, keep splitting a wait into its own task, launched once the
   input exists.

What hazbrief-mcp does now:

1. Run `seldon_prior_art_verify` on `docs/design/2026-11-04_DN-019_the_brief_as_a_live_view_what_is_on_by_default_and_what_the_held_screens_teach.md`
   once seldon's main carries SEL-029. Expect PASS, with line 62 `pass (superseded)`. That records a passing verdict for
   the note's current bytes.
2. DN-019 and its ADDENDUM-01 are already committed, so there is no note to name beside the ledger: the tool refuses
   an unchanged file. `seldon prior-art verify` commits its own verdict line. If a held lease deferred it, the
   dispatcher's next pass commits it with the `prior_art` class sweep (`seldon/core/reconcile.py`). That sweep also
   covers the `state/prior_art_queries.jsonl` and `state/prior_art_verdicts.jsonl` lines dirty since 2026-11-08 ~17:48Z.
3. From now on, when a note or addendum is NEW or edited, commit it with its ledger in one call:
   `seldon_commit_governed(paths=["<the note>", "state/prior_art_verdicts.jsonl"])`.
4. Re-file a task whose Spend must change as `<number>R` with the new Spend line, and withdraw the original.
