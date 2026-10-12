# MODEL-002: a registry role may pin an exact model id; role `author` pins Opus 4.8; ai-readiness-kg's executive summary v2 is registered and its dispatch released

**Repo:** seldon (primary). Cross-repo by absolute path: `/Users/brock/GitHub/ai-readiness-kg` (Part D only). L4: commit, merge, push.
**Date:** 2026-10-12. **Authored by:** a Desktop session in ai-readiness-kg, resuming `handoffs/2026-10-12_executive_summary_brief_dn014_stop_held.md`.
**Governing:** `docs/design/AD-035_config_driven_model_selection.md`, `docs/design/AD-037_in_process_quality_control_for_dispatched_sessions.md`, and the operator's ruling in `/Users/brock/GitHub/ai-readiness-kg/docs/design/2026-10-12_DN-014_executive_summary_brief.md` §9: he can name any model for a role; defaults are the most recent models unless there is a reason otherwise; Opus 4.8 writes the executive summary. Glob and read every sibling `*MODEL-002*ADDENDUM*.md`.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**After:** none
**Model:** primary
**Spend:** est. 1M tokens. Part C's probes are one minimal call per family plus one per pin.
**Network:** none beyond git push.
**Exclusive:** yes

## Step 0

If this task is `in_progress`, stop. Otherwise set it `in_progress` now.

## Measured premises (verify; report any that is wrong)

- `seldon/models.py` at HEAD: a role maps to a family; the lock holds one id per family, the newest the CLI's alias resolves; `check_task_models` accepts only those ids; `load_registry` refuses any role key it does not validate only by family and effort. There is no way to say "this role runs Opus 4.8". A task header naming the id is refused by AD-035-R5, correctly.
- `models/models.lock.yaml` (resolved 2026-10-12, CLI 2.1.296): opus resolves to claude-opus-5-5.
- AD-035 §1 records that Opus 4.8 is still served (as a classifier fallback target). Whether `--model claude-opus-4-8` is served on demand is unmeasured; Part C measures it.
- No calibration report exists under `calibration/reports/` in seldon or ai-readiness-kg.

## Part A: AD-035 ADDENDUM 02

Write `docs/design/AD-035_ADDENDUM_02_pinned_roles.md` (exempt from the AD-036-R4 gate by `*_ADDENDUM_*.md`). Content: the gap above, measured; the operator's ruling quoted from DN-014 §9; prior art by reference to AD-035 §2 (lockfiles carry exact pins beside ranges and record what they resolved to: Cargo `=x.y.z`, an exact version string in `package.json`; MLflow maps a name to a specific version); then these rulings, each as a bold `AD-035-Rn.` line so the register pattern reads it:

- **AD-035-R9.** A registry role may carry `pin: <model id>` beside `family` and `effort`. The pin must start with `claude-<family>-`. A role without a pin follows its family head; R2 is unchanged, and "newest" stays the default.
- **AD-035-R10.** `seldon models refresh` probes every distinct pin with `--model <pin>` and records it under the lock's `pins:` with the served id, `available`, and the evidence file. Served must equal the pin exactly; anything else is `available: false`. A failed pin probe never fails the family probes and never blocks writing the lock.
- **AD-035-R11.** A pinned role resolves to its pin only while the lock marks it available; otherwise resolution fails as `pin_unavailable`, naming the role and the pin. It never falls back to the family head: a silent fallback is the substitution R6 exists to stop.
- **AD-035-R12.** R5 accepts the family ids plus every available pin. The four `ANTHROPIC_DEFAULT_*_MODEL` variables still carry the family heads; `--model` carries the pin; the R6 receipt compares the served id with the pin.
- **AD-035-R13.** AD-037's checker over a pinned role maps by the role's family (an opus pin is read by fable). A calibration report is per judge id over generator id, so `resolve_judge` over a pinned generator needs a report for that pin (AD-037-R5 unchanged).

First use, stated in the addendum: role `author`, family opus, pin claude-opus-4-8, effort high. Effort is an assumption: AD-036-R8 requires a declared level, and the operator's book work ran before the 5.5 move to medium. Record the documented default for that model if the CLI's own help or the lock evidence states one; do not fetch the web for it.

- check: `seldon prior-art verify docs/design/AD-035_ADDENDUM_02_pinned_roles.md` passes or reports the addendum exempt; quote it.
- check: `seldon decision list` shows AD-035-R9 to R13 accepted (`seldon decision accept`, AD-033-R8 statements and validator, `decided_by: desktop`).

## Part B: the mechanism

In `seldon/models.py` and `seldon/commands/models.py`: R9 validation in `load_registry`; R10 pin probes and the lock's `pins:` block in `refresh` (`load_lock` accepts a lock with no `pins:`, so today's lock stays valid); R11 in `resolve_role` with a `PinUnavailable` error whose reason is `pin_unavailable`; R12 in `check_task_models` and `launch_spec`; `seldon models show` prints the pin and its availability per role. Tests with the fake runner and zero model calls:

- check: a pin whose probe is served the pin is available and resolves.
- check: a pin whose probe is served another id is `available: false`, the family probes still write the lock, and resolving the role raises `pin_unavailable`.
- check: removing the no-fallback guard fails a test (AD-032 FC-27).
- check: R5 accepts `**Model:** <pinned role>` while available and refuses it, quoting the lock, while unavailable.
- check: `resolve("checker", generator=<pinned opus role>)` returns the fable id.
- check: a registry pin that does not start with `claude-<family>-` is refused at load.
- check: the full seldon suite, detached and polled; quote passed, skipped, xfailed, deselected, failed.

## Part C: role `author`

Add `author` to `models/registry.yaml` (family opus, pin claude-opus-4-8, effort high; `uses:` naming ai-readiness-kg DN-014 §9 and the operator's book work). Run `seldon models refresh --force` on main.

- check: the lock's `pins:` entry for the pin, quoted, with its evidence file.
- check: `seldon models resolve author` prints the pin.

**If the pin is not available, stop after committing Parts A to C. Do not do Part D. Report it: the operator's chosen author is not served, and choosing another is his value input, not this session's.**

Merge and push Parts A to C to seldon main before Part D; ai-readiness-kg's registration reads the seldon checkout.

## Part D: ai-readiness-kg (absolute path `/Users/brock/GitHub/ai-readiness-kg`)

1. Confirm `.seldon/DISPATCH_STOP` is present and the dispatch lease is free. If the lease is held, stop and report.
2. `git status --porcelain`. Expected untracked: `docs/design/2026-10-12_DN-014_executive_summary_brief.md` and `cc_tasks/2026-10-12_executive_summary_from_brief_v2.md`. Anything else untracked or modified: list it in the RESULT and stop; do not commit what this task did not name.
3. Commit DN-014 alone, path-scoped, through the hooks.
4. `seldon cc register cc_tasks/2026-10-12_executive_summary_from_brief_v2.md`. Its `**Model:** author` must pass R5.
5. `seldon task supersede 78971e58 --superseded-by <v2 id>`, reason: the v2 reads DN-014 as committed and runs on the `author` role, per DN-014 §9.
6. Chain the v2 before `4fd07101` (`seldon task chain <v2 id> 4fd07101`, the CLI form of `seldon_task_chain`).
7. Push. Confirm `git status --porcelain` is empty, then remove `.seldon/DISPATCH_STOP` (Desktop held it for exactly these conditions; the 2026-10-12 handoff's first action, items 1 to 4).

- check: `seldon_query` shows the v2 `proposed`, 78971e58 `superseded` with a `superseded_by` edge to it, and a `precedes` edge from the v2 to 4fd07101.
- check: `git -C /Users/brock/GitHub/ai-readiness-kg status --porcelain` is empty and the STOP file is absent.
- check: `seldon dispatch --dry-run` (or the dispatcher's candidacy read, whichever exists) in ai-readiness-kg names the v2 as a candidate; quote it.

## Report

RESULT under 50 lines at `cc_tasks/2026-10-12_MODEL-002_pinned_roles_author_opus_4_8_RESULT.md`: the addendum's commit and record ids; the suite line; the pin probe (served id, available, evidence path); Part D's commits and graph state, or the line at which it stopped and why; premises found wrong; tokens and model. Then `seldon verify`, `seldon cc complete`, merge, push.
