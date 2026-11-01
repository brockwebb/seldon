# SEL-019: a new consumer project becomes one command (`seldon project new`)

**Status:** proposed
**Author:** the factory Desktop session (FCT-1), 2026-11-01.
**Repo:** seldon. L4: commit, merge, push. No other repo is written.
**After:** none
**Governing:** SEL-010R2 (`seldon dispatch adopt`); SEL-005 (standing dispatcher, "Adopting it in another project"); SEL-016 (the hazbrief adoption, the pattern to repeat); DN-006 decision 10 (no hand dispatch where a dispatcher exists); factory F-008 (one coordinator registers into any repo's queue; a new repo gets at most one hand launch) and F-002.
**Model:** primary
**Spend:** est. 0.5M tokens. Basis: SEL-016 at 0.3M for a hand adoption; this is that sequence as a command with tests. Zero model calls.
**Network:** none beyond git push.
**Framework layer served (DN-005 §5 rule 1):** none (machine infrastructure).
**Exclusive:** no
**Touches:** seldon/commands/, seldon/core/, tests/, docs/design/, CLAUDE.md
**Parts:** A 0.85, B 0.15.
**Premises:**
- premise: the adopt command exists | check: grep -q "\"adopt\"" seldon/commands/dispatch.py
- premise: aacps-ai-policy was adopted by hand (the third such adoption; the evidence for this task) | check: sh -c "grep -q '^dispatch:' /Users/brock/GitHub/aacps-ai-policy/seldon.yaml"

Glob and read every sibling `*SEL-019*ADDENDUM*.md`.

## Stop condition (AD-037-R6, by the dispatcher)

Tokens 0.8M. Stop and report if the command needs a change to `dispatch adopt` itself rather than composing it.

## Why

aacps-ai-policy was scaffolded 2026-10-31 and its first task and corpus acquisition ran before the repo was under seldon; adoption then happened by hand inside AP-02 (2026-11-01, commit 8869c47 there), the third hand adoption after squiddy and hazbrief (SEL-016). The operator's standard (2026-11-01): seldon manages the folder and its state changes, calls squiddy for the graph, and the operator never launches a task in a window. The missing piece is one command that turns a directory into a seldon project with a dispatcher and, optionally, a squiddy graph, so the next consumer repo never starts the wrong way.

## Part A: `seldon project new <path> [--graph <name>] [--dispatch]`

One command that does the SEL-016 sequence for any directory: init, hooks, interpreter config, dispatch adopt, plist, and, with `--graph`, runs `squiddy init` for a graph of that name from the kit's template (the consumer pattern hazbrief and aacps follow: `graphs/<name>/graph.yaml`, config rendered, inbox, manifest). Idempotent: a second run on an adopted project changes nothing and says so. The command registers nothing but reports what the operator or coordinator registers next. Tests: a temp directory becomes a project with a dispatch block and a loadable plist (plist load itself mocked), and a second run is a no-op. Document it in SEL-005's design note under "Adopting it in another project" as the replacement for the hand steps, and in CLAUDE.md's project list.

## Part B: the record

RESULT: the command's usage line, the test names, the design-note section it replaces, and the exact sequence it runs so a reader can compare it with SEL-016 and aacps commit 8869c47.
