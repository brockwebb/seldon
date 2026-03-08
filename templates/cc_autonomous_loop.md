# CC Autonomous Experiment Loop Template

**Derived from:** [karpathy/autoresearch](https://github.com/karpathy/autoresearch) `program.md` pattern
**Purpose:** Template for CC task files where Claude Code runs experiments autonomously.

---

## Instructions for Claude Code

### Setup

1. Read the following files for full context:
   - [LIST FILES TO READ]
2. Verify prerequisites:
   - [LIST PREREQUISITES — data exists, dependencies installed, etc.]
3. Create results log: `results.tsv` with header row
4. Confirm setup, then begin the loop.

### Scope

**What you CAN modify:**
- [LIST EDITABLE FILES / PARAMETERS]

**What you CANNOT modify:**
- [LIST READ-ONLY FILES / FIXED INFRASTRUCTURE]
- Do not install new packages or add dependencies.

### Goal

**Primary metric:** [METRIC NAME] — [lower/higher] is better.
**Budget per experiment:** [TIME OR RESOURCE BUDGET]

### Simplicity Criterion

All else being equal, simpler is better. A small improvement that adds ugly complexity is not worth it. Removing something and getting equal or better results is a great outcome — that's a simplification win.

### Results Logging

Log every experiment to `results.tsv` (tab-separated). Columns:

```
commit	[METRIC]	status	description
```

- commit: git short hash (7 chars)
- [METRIC]: value achieved (use 0.0 for crashes)
- status: `keep`, `discard`, or `crash`
- description: one-line summary of what was tried

### The Loop

LOOP FOREVER:

1. Review current state (git log, results.tsv, latest kept result)
2. Formulate a hypothesis — what change might improve [METRIC]?
3. Implement the change
4. `git commit` with descriptive message
5. Run the experiment: `[RUN COMMAND] > run.log 2>&1`
6. Extract results: `[GREP/PARSE COMMAND]`
7. If empty output → crash. Run `tail -n 50 run.log` for diagnostics.
8. Log results to `results.tsv`
9. If [METRIC] improved → keep (advance branch)
10. If [METRIC] equal or worse → discard (`git reset --hard` to previous keep)
11. GOTO 1

### Crash Recovery

If a run crashes:
- Trivial fix (typo, missing import) → fix and re-run
- Fundamentally broken idea → log as `crash`, revert, move on
- If stuck after 3 attempts on same idea → abandon it

### NEVER STOP

Once the loop begins, do NOT pause to ask if you should continue. The human may be away from the computer and expects you to work indefinitely until manually stopped. If you run out of ideas, think harder — re-read the code, try combining previous near-misses, try more radical changes. The loop runs until interrupted.

---

*Customize the bracketed sections for your specific experiment. Delete this line.*
