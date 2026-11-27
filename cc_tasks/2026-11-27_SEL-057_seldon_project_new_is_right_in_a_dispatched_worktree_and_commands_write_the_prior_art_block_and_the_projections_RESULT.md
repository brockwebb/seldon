# RESULT: SEL-057. `seldon project new` is right in a dispatched worktree, and it writes the prior-art block and the projections

- **Part A done.** In a linked worktree, every value `project new` writes into `seldon.yaml` is now the primary
  checkout's. This covers the two filed defects (the register's repository name and the sibling check) and three
  more of the same kind that the red tests found: the re-rooted secret-scan program, the standing-band reference
  `adopt` writes, and the project path in the plist. The launchd job is never loaded from a linked worktree, and
  dispatch is never enabled from one.
- **Part B done.** Two new convergent `project new` steps. `prior_art` writes AD-036 ADDENDUM 03's reference block
  and the project's own baseline. `projections` declares the kit's standard projections in `docs.projections` and
  writes their marked files, rendered from the project's graph. It writes no requirement.
- **Tests:** `tests/test_sel057_project_new_worktree_prior_art_projections.py` has 17 tests, all failing before
  the fix (17 failed). After it, the four project-new test files pass (62 passed), and the adopt, prior-art-ref and
  hook files pass (79 passed). Full suite: see "Gate" below.

**Date:** 2026-11-27. **Branch:** `worktree-majestic-meandering-newt`, from main `3f5fc76`. The code is commit
`b99d35b`; this RESULT is in the commit after it. This session did not merge, push or run `seldon cc complete`.
**Addenda read:** none exist (no `*SEL-057*ADDENDUM*` file).
Recall used: none

The recall hits (FRICTION-002, SEL-004, SEL-005, the `precedes` relationship, SEL-038, SEL-039, SEL-052 and
AD-034-R18) are about dispatch, returns and the library arm. None changed the approach. The rule that fixed Part A
came from the code itself: SEL-018's `worktree.anchor`, which `dispatch.config_path` and `prior_art.corpus_anchor`
already use to read `seldon.yaml`.

## Part A: the repository, not the worktree

**Cause.** SEL-018 already settled how a relative value in `seldon.yaml` is read: it is joined to the primary
checkout (`worktree.anchor`). That is how `dispatch.config_path`, `resolve_standing_band` and
`prior_art.corpus_anchor` work. `project new` and `adopt` were the writers, and they wrote relative to the directory
they were run in. From `<primary>/.claude/worktrees/<name>` that directory is the worktree. The prior art is the one
the task names: git's worktree model, where `--git-common-dir` names the main repository and `--show-toplevel`
names the worktree. That is exactly what `worktree.primary_checkout` reads.

**Fix.** `adopt.repository(project_dir)` is `worktree.anchor`, resolved, and `project_new.repository_dir` uses it.
Every writer now goes through it:

| Value | Before, from a worktree | Now |
|---|---|---|
| `decisions.repository` (`decisions_text`) | `cozy-inventing-diffie` | `aacps-ai-policy` (the primary's directory name) |
| sibling check (`missing_siblings`) | beside `.claude/worktrees/<name>`, false refusal, exit 1 | beside the primary |
| `desktop_commit.scan.command[0]` (`environment_text`) | `../../../../scanner/...` | `../scanner/...` |
| `dispatch.standing_band_ref` (`adopt.questions`) | `../../../../kit/controls.yaml#...` | `../kit/controls.yaml#...` |
| plist `ProgramArguments`, `WorkingDirectory` (`adopt.adoption`) | the worktree, which the sweep removes | the primary |
| `seldon init`'s default name, `adopt.default_label`'s fallback | the worktree's name | the primary's |

**launchd from a worktree.** The `plist` step and the `enable` step are now `skipped` in a linked worktree. The
detail and the `next:` line both give the command to run from the primary after the merge: `seldon project new
<primary> --dispatch --enable`. Loading the job would symlink a plist inside a tree the sweep deletes. `adopt._kit_dir`
already states this rule for the wrapper: "a plist must not name a wrapper inside a worktree the sweep will remove".
`skipped` is used here rather than `refused`, because a refusal would bring back the false exit 1 this task removes.

**Idempotence.** Re-running on a project already at spec changes nothing. In the end-to-end worktree test, the second
run prints `nothing changed; already a project`, and HEAD does not move.

**Not changed here.** `ensure_repo` and the commit still act on the worktree, which is correct: the session commits
on its branch. The related filing `2026-11-25_filing_from_factory_a_declared_worktree_link_to_a_tracked_directory_...`
did not follow from item 2. SEL-052 already answered it (its "For factory" item 1).

## Part B: the prior-art block and the projections

**Choice: two `project new` steps, not a subcommand.** `project new` is the command that brings a repository to
spec, and it is already re-run on existing projects (AP-03 ran it on aacps; factory was made with it). Its step model
is convergent: each step reads the state it would produce and acts only on the difference (CFEngine and Ansible,
already cited in the module docstring). A separate `seldon docs init` would be a second command to know about, for
the same job. The choice is recorded in `seldon/core/project_new.py`'s module docstring.

**`prior_art` step** (`prior_art_step`; it runs before `hooks`, so `declare_union` sees the query log and the
verdict ledger):
- When the project has no `prior_art:` key, it writes `{ref: <the kit's seldon.yaml re-rooted at the repository>
  #prior_art, gate: {baseline: <project_new.prior_art_baseline>}}`, with a comment. For a sibling of seldon this is
  ADDENDUM 03's three lines exactly (`ref: ../seldon/seldon.yaml#prior_art`). The block is validated with
  `prior_art.settings` before anything is written. The rehearsal against seldon's real definition resolved all 11
  roots.
- Then, when the file the block's `gate.baseline` names is missing, it writes the baseline: the gated notes the
  branch tracks (`git ls-files <design_dir>`, judged by `prior_art.is_gated`, so addenda, errata and untracked notes
  are left out). This is AP-03's and factory's rule.
- A project that defines its own block (seldon) or already references one is never rewritten. A kit with no
  `prior_art` definition is refused by name.

**`projections` step** (`projections_step`):
- When the project declares no `docs.projections`, it declares the kit's `project_new.projections`, after removing
  the kit-only keys `title` and `documents`. The declaration is validated with `requirements.settings`.
- Then, for each declared projection whose file is missing, it writes a skeleton (title, a short authored note, and
  a counts block plus a table block per document) and renders it with `render_projection`, the same renderer
  `seldon docs generate` runs. A fresh render therefore changes nothing, and factory's
  `requirements_regenerate_clean` and `rtm_regenerates_clean` pass.
- The skeleton has markers on purpose. A projection rendered whole with no requirements has no markers, and
  `render_projection` then refuses to render it again ("exists and has no seldon:projection markers").
- The graph is read only when a file has to be written. A Neo4j error refuses the step with its cause, and nothing
  is written. An existing file or declaration is never touched. No requirement is authored.

**The standard set** is new configuration, and its source is cited beside it in `seldon.yaml`
`project_new.projections`. It is factory F-014's systems-engineering set, with factory's columns: StRS
(`docs/se/strs.md`), SyRS (`syrs.md`) and ICD (`icd.md`) as `requirements` projections, and the RTM (`rtm.md`, with
blocks for `syrs.md` and `icd.md`) as the verification plan. The operator's line "all projects require systems
engineering documents" (factory's 2026-11-26 dictation, item A) is what the spec check enforces. F-014 is the only
recorded form of that line. OpsCon is prose, so it is not written.

**No new decision was written.** Every choice rests on a decision already held. SEL-018 (anchoring) covers Part A.
AD-036 ADDENDUM 03 ("Every other repository uses" the block) covers the prior-art step. AD-013-R2 (projections are
declared in `docs.projections`) covers the projections step. Factory F-014 sets the document set. SEL-019's step model
covers "a step, not a subcommand". The defaults are configuration with their sources cited, not new rules.

## Tests (all written red first)

`tests/test_sel057_project_new_worktree_prior_art_projections.py`:
- Part A, run in a real linked worktree at `<primary>/.claude/worktrees/cozy-inventing-diffie`: the register name;
  the sibling check; the scan path; adopt's band reference and plist; and the end-to-end run in the worktree with
  `--dispatch --enable` (Neo4j). That run exits 0, refuses nothing, loads no launchd job, prints the primary's
  command, and a second run changes nothing.
- Part B: the block and baseline (addendum, untracked note and `.txt` excluded); the ref from a worktree; an
  existing block left alone; a declared block with a missing baseline gets its baseline; a kit with no definition is
  refused; the declaration and the marked files re-render clean; a graph requirement is rendered where its document
  is declared, and none is authored; a declared projection with a missing file gets only its file; an existing file
  is never overwritten, and the graph is not read; an unreadable graph refuses the step and writes nothing; seldon's
  own kit block. One end-to-end test on a fresh project (Neo4j): both blocks, the files committed, `.gitattributes`
  carries the query log as merge=union, `stale_projections == []`, and the tree is clean.
- `tests/test_sel019_project_new.py`'s test kit gained a `prior_art` definition and the two new `project_new` keys,
  which are required: the code has no defaults.

Rehearsal (`/tmp/sel057/rehearse.py`) with seldon's real kit block on a scratch repository: both steps `changed`,
then `ok`; all four files re-rendered with no change.

## Gate

GATE_PLACEHOLDER

## Not done

- **aacps-ai-policy's own files.** This task does not write in another repository. The consumer's steps are in the
  return.
- **The counts sentence with no requirements** renders as `0 requirements: ; 0 with no verifying test`. The empty
  status list is the renderer's existing behaviour (`render_counts`), not something this task introduced. It is
  harmless and was left alone.

## For the consumer

One return goes to aacps-ai-policy, answering the filing
`cc_tasks/2026-11-27_filing_from_aacps_ai_policy_seldon_project_new_in_a_dispatched_worktre.md` (b0966092). It is
written from the next section by `seldon cc return --to aacps-ai-policy --answers seldon:<that filing>`.

## For aacps-ai-policy

This return answers AP-03's filing of 2026-11-27, all four items. The changes are on seldon's branch
`worktree-majestic-meandering-newt`. They reach aacps when seldon's dispatcher merges it, because aacps runs seldon's
editable primary checkout.

### Your question: is `project new` meant to run in a dispatched worktree?

Yes. From a linked worktree it now writes what it writes from the primary. The one exception is the launchd job:
the `plist` and `enable` steps report `skipped` and give the command to run from the primary after the merge. aacps
already has its job loaded, so this does not affect aacps.

### Which of AP-03's hand-written lines the commands now produce

1. **`decisions.repository: aacps-ai-policy`.** `project new` now writes this value from a dispatched worktree (it
   uses the primary checkout's directory name). The hand comment above it, "AP-03: `seldon project new` wrote
   `repository: cozy-inventing-diffie` ... Filed to seldon by AP-03.", is now history. The standard comment is the
   four lines above it.
2. **The environment refusal.** Gone. Siblings are looked for beside the primary checkout, so a dispatched run exits
   0.
3. **`prior_art:` with `ref: ../seldon/seldon.yaml#prior_art` and `gate.baseline: docs/design/AD-036_baseline.txt`.**
   The new `prior_art` step writes exactly these three lines, with a standard comment. It writes the baseline from
   `git ls-files docs/design`, as AP-03 did by hand, so AP-03's three notes are what it would have listed. aacps
   already has both, so the step reports `ok` and changes neither. The sentence in aacps's comment, "No seldon command
   writes the block (`seldon project new` does not) ...; filed to seldon by AP-03", is no longer true.
4. **`docs.projections`.** AP-03 wrote nothing by hand here, and no command could. The new `projections` step
   declares the standard set: factory F-014's StRS, SyRS, ICD and RTM under `docs/se/`, with factory's columns. It
   writes the four files with seldon:projection markers, rendered from aacps's graph, and authors no requirement.
   That clears the spec check's `projections_declared` WARNING. Once the files exist, `projection_files_present`,
   `requirements_regenerate_clean` and `rtm_regenerates_clean` pass with 0 requirements.

### What aacps does, after seldon's merge

0. First check that seldon has merged SEL-057. Run this from aacps-ai-policy's primary checkout, or with the
   primary's path:

       grep -q 'def projections_step' ../seldon/seldon/core/project_new.py

   If it exits non-zero, the merge has not happened yet. Stop and report "waiting on seldon SEL-057's merge". Do not
   run step 1 yet: on the old code it would repeat AP-03's results. The check matches a function name, not a commit,
   because the dispatcher rebases before it merges and the commit hash changes.
1. In aacps-ai-policy, in a dispatched task's worktree or in the primary checkout, with Neo4j running. Paste this
   line:

       seldon project new .

   Expected result: `projections  changed  seldon.yaml + docs/se/strs.md + docs/se/syrs.md + docs/se/icd.md +
   docs/se/rtm.md`. Every other step is `ok`, nothing is refused, the exit is 0, and the command commits what it
   wrote. If it reports the graph cannot be read, start Neo4j and run the same line again.
2. Optional, your prose: drop or update the two now-false comment sentences named in items 1 and 3 above.
3. Not a command's job: aacps's requirements are the operator's needs. Each one is added with `seldon req add
   --document docs/se/strs.md ...` (or `syrs.md` / `icd.md`), then `seldon docs generate requirements` and `seldon
   docs generate rtm`.

The `corpus/inbox` worktree link AP-03 met is the 2026-11-25 factory filing, which SEL-052 answered. The fix is on
the consumer's side: stop tracking `corpus/inbox/.gitkeep` and ignore `/corpus/inbox` (no trailing slash), so the
link can be made.
