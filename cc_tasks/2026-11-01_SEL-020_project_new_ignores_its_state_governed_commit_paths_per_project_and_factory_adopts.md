# SEL-020: `project new` ignores its own state, the governed commit takes per-project paths, and factory adopts Seldon

**Status:** proposed
**Author:** the factory Desktop session (FCT-2), 2026-11-01.
**Repo:** seldon (L4: commit, merge, push). Also writes /Users/brock/GitHub/factory, only through Part C's steps.
**After:** none
**Governing:** factory `docs/plan.md` stage 1 and `docs/gaps.md` G-02, G-03, G-04 (commits f0db70e, dd68f55); factory F-012 (no repo adopted by hand), F-006 and F-007 (API-billed runs), F-003; SEL-019 (`project new`); DD-007 (dispatch is Max OAuth only).
**Model:** primary
**Spend:** est. 0.6M tokens. Basis: SEL-019 estimated 0.5M for the command itself; this is two small changes to it plus one adoption. Zero model calls.
**Network:** none beyond git push.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** no
**Touches:** seldon/commands/, seldon/core/, seldon/mcp/, tests/, docs/design/, CLAUDE.md, /Users/brock/GitHub/factory
**Parts:** A 0.2, B 0.4, C 0.25, D 0.15.
**Premises:**
- premise: `project new` exists | check: test -f seldon/core/project_new.py
- premise: factory is not yet a seldon project | check: sh -c "test ! -f /Users/brock/GitHub/factory/seldon.yaml"
- premise: factory's API key file is inside the repo (DD-007 would refuse its dispatcher) | check: sh -c "grep -q ANTHROPIC_API_KEY /Users/brock/GitHub/factory/.env"

Glob and read every sibling `*SEL-020*ADDENDUM*.md`.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.9M. Stop and report if Part B would loosen the governed commit for a project that does not declare
`desktop_commit.paths` (existing projects must behave exactly as today), or if Part C finds uncommitted work in
factory that this task did not write (F-003: stop and say so).

## Why

The factory repo holds the portfolio's decisions, friction log and cross-repo reviews, but it is not a Seldon
project: its decisions bind nothing, a Desktop thread cannot commit there through the governed hook (FCT-2 fell
back to device-shell git, which leaves lock files it cannot delete), and the factory view (plan stage 4) needs a
dispatcher to be built. Two defects in `project new` stand in the way: it leaves `.seldon/` unignored (aacps
carried it in `.git/info/exclude`), and the governed commit only accepts seldon's own layout.

## Part A: `project new` writes the `.seldon/` ignore line

Step 5 (or the step that writes ignore lines) adds `.seldon/` to the project's `.gitignore` when absent, and
commits it with the rest of the run's paths. Test: a fresh directory through `project new --dispatch` followed by
one `dispatch once --dry-run` leaves `git status --porcelain` empty.

## Part B: `desktop_commit.paths`, a per-project allowlist for the governed commit

`seldon_commit_governed` (and its CLI path) reads an optional `desktop_commit.paths` list from the project's
`seldon.yaml`. Absent: today's fixed set (docs/design/, cc_tasks/, handoffs/, issues/, ontology/, plus the
register rule), unchanged. Present: that list replaces the fixed set; the secret scan, the hooks and the register
rule still apply. Tests: a project without the key refuses `README.md` exactly as today; a project declaring
`[friction-log.md, docs/]` commits `friction-log.md` and `docs/x.md` and still refuses `scripts/x.sh`; a declared
path holding a planted secret is refused by the scan.

## Part C: factory adopts Seldon

1. Move the API key out of the repo before anything else. Create `~/.config/factory/` and move
   `/Users/brock/GitHub/factory/.env` to `~/.config/factory/api.env` (mv, not copy; never print its contents).
   Change `factory/scripts/api_review.sh` (and any other script under `factory/scripts/` that reads the key) to
   source `~/.config/factory/api.env` and refuse without it; drop the `factory/.env` and `~/.env` fallbacks. Update
   `factory/.env.example` to say where the key lives. Amend nothing in `decisions.md`; the coordinator records the
   F-006 change.
2. `seldon project new /Users/brock/GitHub/factory --dispatch --enable` with no graph. If it needs a branch or a
   database name, use `main` and `seldon-factory`.
3. In factory's `seldon.yaml`, declare `desktop_commit.paths: [decisions.md, friction-log.md, registry.md,
   README.md, docs/, reviews/, experiments/, handoffs/, cc_tasks/, scripts/]` and commit it.

Test: after one dispatcher pass, factory's `git status --porcelain` is empty and `dispatch status` shows a pass
with no refusal; `grep -r ANTHROPIC_API_KEY /Users/brock/GitHub/factory` finds only `.env.example` text with no
value; `api_review.sh` with the key file renamed away exits nonzero before launching anything; a second
`project new` run reports `ok` on every step.

## Part D: the record

RESULT: the test names; factory's commit ids; the `dispatch status` output after the first pass; the exact
`desktop_commit.paths` written; where the key now lives (path only).
