# `seldon dispatch` — the standing dispatcher

**Date:** 2026-09-15. Seldon-side record of a command group built for `ai-readiness-kg` and
usable by any project that opts in. The design note is that project's
`docs/design/2026-09-15_DN-006_standing_dispatcher.md`; its §3 decisions are the spec and this
file says what landed here, what a second project must do to use it, and the two places the
build found the note wrong.

## The condition

A registered `ResearchTask` whose gate was clean sat in `proposed` until a person relayed a
dispatch line into Claude Code. Nothing about *which* task to run was missing — the graph
already held the answer — only the act of starting it. That is a latency defect, and it is the
only one this closes: reading a RESULT, naming its wrong premises and authoring the next task
is still a Desktop OODA and is not automated here (DN-006 §4).

## Shape

```
seldon dispatch once [--dry-run]   one evaluation pass, at most one launch, exit
seldon dispatch status [--json]    the live criteria vector for every open task
seldon dispatch lease show         the lease body; takes no lock
seldon dispatch lease reap         operator-only; refuses while the holder PID is alive
```

There is no daemon. **launchd is the loop and `once` is the pass** — the pattern
`scripts/jobs/biblio_resume_job.py` already runs under in that project. A daemon would add a
process to supervise and would not make anything happen sooner than the poll interval does.

`seldon/core/dispatch.py` holds everything pure or filesystem-local: candidacy, the nine
criteria, the config and its reference resolution, the lease. `seldon/commands/dispatch.py` is
argument parsing, the graph reads, the claim and the launch. The split is what lets each
criterion be tested against a fixture task file that fails exactly that one; a monolithic
evaluator can only be tested end to end, and an end-to-end test that goes red does not say
which criterion said no.

**The graph is the queue.** There is no second table to keep in step. A task becomes
dispatchable by being registered with a `source_file` whose task file carries the headers —
opt-in, so installing the job changes the behaviour of nothing already queued.

## Configuration: the `dispatch:` block

Per project, in that project's `seldon.yaml`. Every key is required; there are no defaults,
because a dispatcher that guessed a branch or a permission mode would be guessing about what a
headless session may do to a checkout.

| key | what it is |
|---|---|
| `enabled` | the kill switch. Must be a real bool — a truthy string is refused, because a kill switch nobody can read is not one |
| `branch` | the branch a pass will dispatch on; any other branch fails c7 |
| `standing_band_ref` | `<file>#<dotted.path>`, e.g. `controls.yaml#spend.daily_tokens`. A **reference**, never a copied number |
| `poll_interval_s` | what the plist should use; recorded here so the value and its reason live together |
| `permission_mode` | the `claude --permission-mode` value a dispatched session runs under, with its reason in a comment |
| `stop_file`, `lease_file`, `log_dir` | paths relative to the project root |
| `cli`, `model` | optional overrides of the `claude` binary and the model |

`enabled` and the STOP file are read on **every** pass and never cached. A cached kill switch is
an advisory one.

## The nine criteria

Eight are DN-006 decision 2's table. The ninth is ADDENDUM_01 to the implementing task, which
binds that project's DN-005 §5 rule 1 — every task names the framework layer it advances, or
says it is hygiene — to something other than a reader's attention.

**Candidacy comes first and is not a criterion.** A task file must carry `**Spend:**`,
`**Network:**` and `**Framework layer served`, and the third must name a layer (`§2.1`–`§2.5`),
a capability tier (`Tier M|O|D`) or `none`. A file without them is **not a candidate** — not
"ineligible" — and `status` says which header failed. The dispatcher does not judge whether the
named layer is the right one; it asserts that a layer was named, which is what the rule
requires and what a reader would otherwise check by hand.

Each criterion is recorded as a **value**, never a boolean summary: "the tree was dirty" is not
actionable and "the tree was dirty on these three paths" is. The whole vector goes on the
`dispatch_launched` event, so a stranger can replay why anything ran.

## Events

On the project's own Seldon log: `dispatch_launched`, `dispatch_finished`, `dispatch_refused`,
`dispatch_observed_stop`. **A pass in which nothing is eligible writes no event** — the log
records assertions, and "nothing to do" is not one; a five-minute poll that logged its own
silence would bury every assertion in it. `status` writes nothing at all: looking is not an
assertion.

## The lease

`fcntl.flock` on `<project>/.seldon/dispatch.lock`, holder `dispatcher:<host>:<pid>`. A second
`once` that cannot take it exits **0** with a `dispatch_refused` — a healthy no-op, the same
contract the burn's cap exhaustion has, so launchd does not learn to treat a normal outcome as
a failure.

`lease reap` is the only release path other than process exit and it **refuses while the holder
PID is alive**. No age-based reap, adopted unchanged from that project's DD-022 orphan rule: an
age threshold releases a lease a healthy long-running holder still needs, and two dispatchers
believing they are one is the defect the lease exists for (DD-019: one ceiling enforced per
shard, 22.0M tokens spent against a 12M ceiling).

## Two places the build found DN-006 wrong

1. **`proposed -> in_progress` is not an edge on the ResearchTask state machine.**
   `seldon/domain/research.yaml` has `proposed: [accepted, rejected, superseded, withdrawn]`.
   Decision 4 calls the claim "the `in_progress` transition"; from `proposed` it is two, and the
   claim marker lands on the second. `CLAIM_PATH` is that walk, the same shape
   `walk_to_completed` already uses for the close path. Recorded in the note's ADDENDUM_01.
2. **Decision 5's permission mode could not be derived from how the project already runs
   `claude -p` unattended.** Its one unattended invocation (`kg/extraction/model_stub.py`) runs
   `--allowed-tools ""` from a hermetic empty cwd: no tools at all, deliberately. That is
   evidence the project has **never** run a tool-executing headless session, so there was
   nothing to derive and the value comes from the CLI's own interface. Also in ADDENDUM_01.

## Adopting it in another project

Add a `dispatch:` block to that project's `seldon.yaml` with `enabled: false`, gitignore the
lease and the log directory, install a launchd plist that runs `seldon dispatch once` from the
project root, and author task files with the three headers. Nothing else in the project
changes, and nothing already queued becomes dispatchable.

## Tests

`tests/test_dispatch.py` (57): configuration and reference resolution, candidacy and each
header, every criterion against a fixture failing exactly that one, the marker regex against
both the new spelling and the one historical spelling found in the surveyed repository, the
lease against a **real second process**, and reap's PID gate.

`tests/test_dispatch_launch.py` (14, Neo4j): the claim/launch/finish path with a stub `claude`
that is a shell script — zero model calls, no network — the three ways a session fails to
finish, the zero-retry assertion (a failing stub run twice, one launch), both kill switches,
the lease refusal, the DD-007 API-key refusal before any claim, and the byte-identical log
after a pass with nothing eligible.
