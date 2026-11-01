# SEL-019: aacps-ai-policy adopts seldon and the standing dispatcher, and a new consumer project becomes one command

**Status:** proposed
**Author:** the factory Desktop session (FCT-1), 2026-11-01.
**Repo:** seldon (primary, where the task is tracked); aacps-ai-policy (seldon.yaml, dispatch block, launchd plist, task registrations; commit there through the hooks). L4: commit, merge, push in seldon; commit on main in aacps-ai-policy.
**After:** none
**Governing:** SEL-010R2 (`seldon dispatch adopt`); SEL-005 (standing dispatcher, "Adopting it in another project"); SEL-016 (the hazbrief adoption, the pattern to repeat); DN-006 decision 10 (no hand dispatch where a dispatcher exists); factory F-008 (one coordinator registers into any repo's queue; a new repo gets at most one hand launch) and F-002.
**Model:** primary
**Spend:** est. 0.8M tokens. Basis: SEL-016 at 0.3M for one adoption, plus Part B (a new command with tests). Zero model calls.
**Network:** none beyond git push.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** yes (writes another repo's seldon.yaml and loads a launchd agent)
**Parts:** A 0.40, B 0.50, C 0.10.
**Premises:**
- premise: aacps-ai-policy has no seldon.yaml | check: sh -c "! test -f /Users/brock/GitHub/aacps-ai-policy/seldon.yaml"
- premise: the adopt command exists | check: grep -q "\"adopt\"" seldon/commands/dispatch.py
- premise: aacps-ai-policy carries AP-01 (closed by its RESULT) and AP-02 with dispatch headers | check: sh -c "test -f /Users/brock/GitHub/aacps-ai-policy/cc_tasks/2026-10-31_AP-01_RESULT.md && grep -q '^\*\*Parts:\*\*' /Users/brock/GitHub/aacps-ai-policy/cc_tasks/2026-11-01_AP-02_admit_the_corpus_extract_and_test_the_anchors.md"

Glob and read every sibling `*SEL-019*ADDENDUM*.md`.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 1.2M. Stop and report if adoption needs a change to the dispatcher's own code beyond Part B's new command, or if the aacps commit hooks refuse for a reason other than a missing interpreter (set `git config seldon.python` there as the other consumers have it).

## Why

aacps-ai-policy was scaffolded 2026-10-31 and its first task (AP-01) and the corpus acquisition ran before the repo was under seldon: nothing is in a project graph. The operator's standard (2026-11-01): seldon manages the folder and its state changes, calls squiddy for the graph, and the operator never launches a task in a window. The missing piece is not aacps-specific: no single command turns a directory into a seldon project with a dispatcher, so every new consumer repo starts the same wrong way. SEL-016 did this by hand for hazbrief; Part B makes it a command.

## Part A: adopt aacps-ai-policy now (the SEL-016 pattern)

`seldon init` in `/Users/brock/GitHub/aacps-ai-policy` (database `seldon-aacps-ai-policy`, per the one-database-per-project convention), `seldon hooks install`, `git config seldon.python` as hazbrief sets it, `seldon dispatch adopt` with the same dispatch block shape as hazbrief's (bypassPermissions, STOP file, lease, per-task logs), the launchd plist written and loaded, one observed pass of the dispatcher reporting the queue. Register `cc_tasks/2026-10-31_AP-01_scope_corpus_and_graph_spec.md` and close it against its RESULT (`cc complete`), so the history is in the graph; register `cc_tasks/2026-11-01_AP-02_admit_the_corpus_extract_and_test_the_anchors.md` as proposed. Commit the adoption in aacps through its hooks. AP-02 then launches on the dispatcher's next pass; do not launch it here.

## Part B: `seldon project new <path> [--graph <name>] [--dispatch]`

One command that does Part A for any directory: init, hooks, interpreter config, dispatch adopt, plist, and, with `--graph`, runs `squiddy init` for a graph of that name from the kit's template (the consumer pattern hazbrief and aacps follow: `graphs/<name>/graph.yaml`, config rendered, inbox, manifest). Idempotent: a second run on an adopted project changes nothing and says so. The command registers nothing but reports what the operator or coordinator registers next. Tests: a temp directory becomes a project with a dispatch block and a loadable plist (plist load itself mocked), and a second run is a no-op. Document it in SEL-005's design note under "Adopting it in another project" as the replacement for the hand steps, and in CLAUDE.md's project list.

## Part C: the record

RESULT: aacps dispatcher state and its first pass; AP-01 closed and AP-02 proposed in `seldon-aacps-ai-policy`; the new command's usage line; a one-line note to the factory (`/Users/brock/GitHub/factory/registry.md` gets `aacps-ai-policy | ... | seldon-aacps-ai-policy | yes`, written and committed by this task, which is the one cross-repo write it makes beyond aacps).
