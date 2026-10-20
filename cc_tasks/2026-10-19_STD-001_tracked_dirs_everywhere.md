# STD-001: cc_tasks/ and handoffs/ are tracked in every repository; `seldon verify` refuses a `.gitignore` that says otherwise; the 29 repos that disagree are corrected in one pass

**Repo:** seldon (primary). Cross-repo by absolute path: every git repository directly under `/Users/brock/GitHub/` (34 on 2026-10-19). L4: commit and push in every repo touched. Work on your worktree branch in seldon; in the other repositories commit on main directly, by path, through their hooks.
**Date:** 2026-10-19. **Authored by:** a Desktop session in squiddy (SQ8).
**Governing:** operator rulings 2026-09-25 (regs-comment-pipeline/.gitignore:14), 2026-10-12 and 2026-10-14 ("stop adding things untracked; everything should be tracked; commit everything"); `~/GitHub/CLAUDE.md` §6.1 (written 2026-10-19 from those rulings); AD-036-R11 (an automatic writer commits what it writes); FC-02 (every handoff is secret-scanned before commit); AD-038-R6. Write the ruling as **AD-039** in seldon with the survey below as evidence; it is a one-ruling note.
**After:** none
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Model:** primary
**Spend:** est. 0.4M tokens. Basis: one verify check with tests, one note, and a scripted sweep over 29 `.gitignore` files plus the secret scan and commit of whatever those directories already hold. The floor is 131K (AD-037-R11).
**Parts:** A 0.3, B 0.5, C 0.2.
**Network:** none beyond git push.
**Exclusive:** yes
**Premises:**
- premise: the standards file carries 6.1 | check: `grep -q "6.1 cc_tasks/ and handoffs/ are tracked" /Users/brock/GitHub/CLAUDE.md`
- premise: the secret scanner is importable from squiddy's venv | check: `/Users/brock/GitHub/squiddy/.venv/bin/python -c "import squiddy.secret_scan"`
- premise: a repo that still ignores both exists | check: `grep -qx "cc_tasks/" /Users/brock/GitHub/CoolSpot/.gitignore`

Glob and read every sibling `*STD-001*ADDENDUM*.md`.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.55M. A repository whose secret scan flags a file is left untouched and listed; the task does not stop for it.

## The survey (2026-10-19, read from every `.gitignore` under ~/GitHub)

Both tracked: arnold, regs-comment-pipeline, seldon, slosh-pipe, squiddy (5). cc_tasks tracked, handoffs ignored: ai-readiness-kg, hazbrief-mcp, icsp_notebook, resume-redactor (4). Both ignored: CoolSpot, TickBiteRisk, ai-workflow-design, appraisal-agent, book_responsible_ai, census-mcp-server, central_library, federal-survey-concept-mapper, ms-teams-attendance-reporter, sas_graph_code_conversion, usai-harness, wintermute, watermarks-remover (deny-by-default allow-list) (13). One side ignored: brock_projects, survey-dag-extractor, usai-api-tester (3). Silent: AI-Pulse, ai-demos, census-web-concept-inventory, dixie, measuring-ai-economy, practical-ai-ml-labs, trustgraph-fork, webdesktop, claude-skills (9). Stale text that still says "gitignored": `~/GitHub/CLAUDE.md` §6 (corrected 2026-10-19), `seldon/CLAUDE.md:230-231`, `seldon/seldon.yaml:86`, `seldon/docs/design/AD-036_ADDENDUM_01_self_test.md:23`, `hazbrief-mcp/CLAUDE.md` Layout, `hazbrief-mcp/BOOTSTRAP.md` step 4. The source of the spread was §6; TickBiteRisk's `.gitignore` cites it by name.

## Part A: the ruling and the check

1. AD-039, one ruling: in every repository Seldon serves or scaffolds, `cc_tasks/` and `handoffs/` are tracked; only `*.json` and `*.jsonl` under them are ignored, by size; a handoff is committed only after `squiddy.secret_scan` passes. Evidence: the survey above and the three operator rulings. Prior-art receipts per AD-036 (the internal arm will find arnold's 2026-08-13 and seldon's 2026-10-04 `.gitignore` comments and FC-02).
2. `seldon verify` gains one check: the repository's `.gitignore` (and any nested one on the path) must not match `cc_tasks/`, `handoffs/`, or any file under them other than `*.json` / `*.jsonl` (use `git check-ignore` against `cc_tasks/probe.md` and `handoffs/probe.md`). A match is a finding named `tracked_dirs_ignored` that quotes the offending line and the fix. `seldon init` writes the correct four-line stanza into a new repo's `.gitignore` (creating the file if absent) and stops printing only the `.env` note.
3. Fix the stale text in seldon: `CLAUDE.md:230-231`, `seldon.yaml:86`, `AD-036_ADDENDUM_01_self_test.md:23` (an erratum line, not a rewrite).
4. Tests, failing on HEAD: verify refuses a temp repo whose `.gitignore` holds `handoffs/`; passes one whose stanza is the four blob lines; `seldon init` on an empty temp dir leaves a `.gitignore` that passes the check.

Acceptance:
- `check: pytest tests/test_std001_tracked_dirs.py -q`
- `check: test -f docs/design/AD-039_tracked_dirs.md`
- `check: ! grep -n "(gitignored)" CLAUDE.md | grep -qiE "handoffs|cc_tasks"`

## Part B: the sweep

1. For each of the 29 repositories above (not the 5 already correct), in one script run from this session by absolute path: rewrite the `.gitignore` so neither directory is ignored, add the four blob lines with a one-line comment citing AD-039, remove any `!handoffs/.gitkeep` line that is now redundant. For watermarks-remover's allow-list, add the two directories to the allow-list. For a repo with no `.gitignore` and neither directory, do nothing.
2. Then, in the same repo: run `squiddy.secret_scan` over every file now untracked under `cc_tasks/` and `handoffs/`. If it passes, `git add` those directories and the `.gitignore`, and commit as `std-001: track cc_tasks/ and handoffs/ (AD-039)` through the repo's hooks; push if the repo has a remote. If it flags, commit the `.gitignore` alone, leave the files, and list the repo, the file and the line number (never the value) in the RESULT.
3. Fix the stale text in hazbrief-mcp (`CLAUDE.md` Layout bullet, `BOOTSTRAP.md` step 4) in the same commit as its `.gitignore`.
4. Record per repo: files newly tracked (count), bytes, scan result, commit sha, in `docs/evidence/std001/sweep.jsonl`.

Acceptance:
- `check: test -s docs/evidence/std001/sweep.jsonl`
- `check: ! git -C /Users/brock/GitHub/CoolSpot check-ignore -q cc_tasks/probe.md`
- `check: ! git -C /Users/brock/GitHub/hazbrief-mcp check-ignore -q handoffs/probe.md`
- `check: ! git -C /Users/brock/GitHub/TickBiteRisk check-ignore -q handoffs/probe.md`

## Part C: the standards file

1. `~/GitHub/CLAUDE.md` is not in a repository. Say in the RESULT whether it is a symlink into one (check `readlink`); if it is, commit the 6.1 edit there. If it is a plain file, record its sha256 in the evidence and leave it.

Acceptance:
- `check: grep -q "AD-039" /Users/brock/GitHub/CLAUDE.md`

## Report

RESULT under 25 lines: the verify finding name and the init stanza; the sweep table (29 rows: repo, files tracked, scan, sha); repos left with flagged files; tokens against 0.4M.
