# AD-039: cc_tasks/ and handoffs/ are tracked in every repository

Executing session of STD-001R (`729a80ba`), 2026-10-19, from the operator's rulings of 2026-09-25, 2026-10-12 and
2026-10-14. **Amends:** `~/GitHub/CLAUDE.md` §6 (withdrawn there as §6.1, 2026-10-19), AD-036 ADDENDUM 01 §1 (an
erratum line). **Implements:** AD-036-R11 for the record directories; FC-02. **Governs:** STD-001R.

## 1. The ruling

### AD-039-R1. The record directories are tracked; only blobs under them are ignored; handoffs are scanned.

In every repository Seldon serves or scaffolds, `cc_tasks/` and `handoffs/` MUST be tracked. The only ignore rules
that may match anything under them are `cc_tasks/*.json`, `cc_tasks/*.jsonl`, `handoffs/*.json` and
`handoffs/*.jsonl` (data blobs, ignored by size). A handoff is committed only after `python -m squiddy.secret_scan`
passes on it; the scan, never an ignore rule, is what keeps a secret out of a public repository. `seldon verify`
refuses a repository where git would ignore `cc_tasks/probe.md` or `handoffs/probe.md` (finding
`tracked_dirs_ignored`, Tier A), and `seldon init` writes the four blob lines into a new project's `.gitignore`.

## 2. Evidence

**The rulings.** 2026-09-25 (quoted at `regs-comment-pipeline/.gitignore:14`: "cc_tasks/ and handoffs/ ARE tracked,
per the operator (2026-09-25). Standards Section 6 says otherwise and is being corrected"); 2026-10-12 and
2026-10-14 ("stop adding things untracked; everything should be tracked; commit everything").

**The survey** (STD-001R, every `.gitignore` under `~/GitHub`, 2026-10-19). Both tracked: 5 (arnold,
regs-comment-pipeline, seldon, slosh-pipe, squiddy). `cc_tasks/` tracked and `handoffs/` ignored: 4. Both ignored:
13. One side ignored: 3. Silent: 9. Stale text that still said "gitignored": `~/GitHub/CLAUDE.md` §6, seldon
`CLAUDE.md` Key Directories, seldon `seldon.yaml` (prior-art roots comment), AD-036 ADDENDUM 01 §1, hazbrief-mcp's
`CLAUDE.md` and `BOOTSTRAP.md`. The spread had one source: §6 of the standards file, which TickBiteRisk's
`.gitignore` cites by name. The sweep's per-repository record is `docs/evidence/std001/sweep.jsonl`.

**The precedents this generalizes.** arnold's `.gitignore` (handoffs tracked since 2026-08-13, cc_tasks since
2026-08-16: "Data blobs dropped into handoffs/ stay ignored: SIZE, not privacy"); seldon's `.gitignore` (handoffs
tracked since 2026-10-04, SQ-008, FC-02: "evidence is never left outside the record"). AD-039 adds nothing to
either rule except that it holds everywhere and that a machine checks it.

**Why a check and not a convention.** The convention already existed twice (arnold, seldon) and did not spread;
the wrong rule did, because it was written in the file every new repository copied. Registration commits a task
file (SEL-006) and `seldon handoff` commits a handoff (DESK-001); an ignore rule over either directory makes both
writers fail or, worse, `git add` without `-f` skips the file and the record is silently absent. Whether a path is
ignored is decided by git itself (`git check-ignore --no-index -v`, which reads every `.gitignore` on the path,
`.git/info/exclude` and `core.excludesFile` in git's precedence order and reports the matching source line), not by
re-implementing gitignore matching.

## 3. Prior art

### External

- library receipt: query "version control of agent session logs and task records secret scanning before commit" | release library_graph_20261017_sq018_02_2026-10-17.json sha256:99984ba3da90146a73ab4e9d8ddf15687551cb2cc2659be90d16e525253ecfb5 | rows lesson:2026-02-22_arXiv_2506_12508#p26:373:1880-4260, lesson:2026-05-09_10_1145_3805621_3807648#p12:247:2585-2737, lesson:2026-02-22_arXiv_2507_21046#p52:716:1007-1689

The library's hits are on the principle, not the mechanism: unified version histories for every agent component
(arXiv 2506.12508), validated updates committed "at explicit, logged commit points" (10.1145/3805621.3807648), and an
"Immutable Audit Trail" with "Version Control for Safe State" (arXiv 2507.21046). The mechanism is git's own
(`gitignore(5)`, `git-check-ignore(1)`); the scan-before-commit step is the pre-commit secret-scanning pattern FC-02
already adopted (`squiddy.secret_scan`). Nothing here is novel; the ruling is a correction of a local standard.

### Internal

- internal receipt: query "handoffs tracked FC-02" | repo seldon@f17ff1e0a4307a5ab5776947b9a8e67cd480e992 | hits docs/decisions/BASELINE_DB-1.md:14, docs/decisions/REGISTER.md:9
- internal receipt: query "handoffs tracked FC-02" | repo squiddy@5eff89511f3191729b31b41f94353802e92fbe03 | hits none
- internal receipt: query "handoffs tracked FC-02" | repo arnold@f089fc8c79403a5371c823c6c3f2aec30fa90e57 | hits none
- internal receipt: query "handoffs tracked gitignore secret scan" | repo squiddy@5eff89511f3191729b31b41f94353802e92fbe03 | hits docs/decisions/REGISTER.md:9
- internal receipt: query "handoffs tracked gitignore secret scan" | repo ai-readiness-kg@788400fd7046eafb6e7855e7867e389f2c4bf45b | hits none
- internal receipt: query "handoffs tracked gitignore secret scan" | repo icsp_notebook@ccfb76201f842fb968e7abc1a513d5d1aefdb405 | hits none
- internal receipt: query "handoffs tracked gitignore secret scan" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits none

The internal arm's include set does not cover `.gitignore` files, so arnold's 2026-08-13 and seldon's 2026-10-04
comments (quoted in §2) are cited from the files directly. The arm finds FC-02 in seldon's decision register, which
is the scan-before-commit half of R1.

## 4. Code

`seldon/core/tracked_dirs.py` (the probe, the stanza, `ensure_stanza`); `seldon/commands/verify.py`
`check_tracked_dirs` (Tier A); `seldon/commands/init.py` step 5. Tests: `tests/test_std001_tracked_dirs.py`.
