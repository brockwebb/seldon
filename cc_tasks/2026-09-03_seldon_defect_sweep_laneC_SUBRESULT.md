# Lane C sub-RESULT — ResearchTask lifecycle (`a3ba67a3` + `1a23fd00`)

**Date:** 2026-09-03
**Task:** `cc_tasks/2026-09-03_seldon_defect_sweep_registry_lifecycle_ontology.md` §4
**Lane:** C — task state machine, `seldon task` CLI group, MCP task tools, their tests
**Design decision recorded as:** AD-028 (referenced in `research.yaml` comments; the AD
document itself is the integrator's to write — see *Cross-lane needs*).

---

## 1. C1 finding — where the `superseded` rows came from

### The task file's premise was stale in two ways

1. **"`a3ba67a3` claims no such state exists" is wrong.** `superseded` has been a
   first-class terminal state in the `ResearchTask` state machine since commit
   `9612b3b` (`feat(state): add superseded terminal state to ResearchTask SM`,
   **2026-06-18 09:37:01 -0400**). `git log -S superseded -- seldon/domain/research.yaml`
   returns that commit as the introducing change. The in-file comment cites
   `cc_tasks/2026-06-18_cc_task_researchtask_superseded_terminal.md`. It was already
   reachable from `proposed`/`accepted`/`in_progress`/`blocked` and already
   unreachable from `completed`/`verified`. `seldon_task_update`'s MCP docstring has
   documented it since then too.

2. **The count is 31, not 30.** Live state distribution of `ResearchTask` in
   `seldon-ai-readiness-kg`:

   | state | count |
   |---|---|
   | completed | 58 |
   | **superseded** | **31** |
   | proposed | 9 |
   | accepted | 1 |

   The discrepancy is not an error in the task file — it is drift. Ordering the 31
   supersede events by timestamp shows 30 of them landed on or before
   `2026-09-01T01:41:27Z` and the 31st landed at `2026-09-02T20:09:30Z`, i.e. after
   the premise was written. **"30" was true when the task file was authored.** This is
   the state-word verification rule paying for itself.

### They were NOT written by a bypass path — evidence

Read directly from the ai-readiness-kg event store
(`/Users/brock/GitHub/ai-readiness-kg/seldon_events.jsonl`, 10,521 events):

- **31** events of type `artifact_state_changed` with `payload.to_state == "superseded"`,
  across **31 distinct `artifact_id`s** — one event per row, no duplicates, no
  orphans.
- **Every one** has `payload.from_state == "proposed"` — a transition the state
  machine has permitted since 2026-06-18.
- **Zero** `artifact_created` events with `to_state == "superseded"`. Nothing was
  born into the state.
- Actor split: **8 `desktop`** (MCP `seldon_task_update`) + **23 `human`**
  (CLI `seldon task update`). All `authority: accepted`. All carry a `session_id`.
- Timestamps span `2026-07-03T17:05:39Z` → `2026-09-02T20:09:30Z`, in three visible
  bursts (7 in early July via Desktop, 23 in one CLI sweep on 2026-08-31, 1 on
  2026-09-01, 1 on 2026-09-02).

Sample event, verbatim:

```json
{"event_id": "5c5f1fa4-c1b8-4b69-9362-dff054c333e2", "event_type": "artifact_state_changed",
 "timestamp": "2026-07-03T17:05:39.673830Z", "session_id": "59c35f17-...",
 "actor": "desktop", "authority": "accepted",
 "payload": {"artifact_id": "fc94ae2f-...", "artifact_type": "ResearchTask",
             "from_state": "proposed", "to_state": "superseded"}}
```

**Conclusion: the 31 rows went through the legitimate state machine via the
event-then-write path. There is no bypass, no paper-sync side door, and no bulk
registrar writing state directly.** The defect `a3ba67a3` described was a
*documentation/awareness* gap (the state existed but was undiscoverable from the CLI —
there was no `seldon task supersede`, so the only way to reach it was
`task update --state superseded`), not a data-integrity gap.

### Adjacent finding, NOT fixed here (Lane D owns it)

7 of the 31 superseded rows carry the description
`**Immutable once written. Changes require a new task file.**`. That is the
`seldon cc register` description-parser defect (task file §5, D3), not a lifecycle
defect. Left untouched — `seldon/commands/cc.py` is Lane D's file.

### Superseded rows lacking a `terminal_reason`

Per the task file, these are a **recorded finding, not something to backfill**:

| database | terminal rows | lacking `terminal_reason` |
|---|---|---|
| `seldon-ai-readiness-kg` | 31 superseded, 0 withdrawn | **31 of 31 (100%)** |
| `seldon-seldon-self` | 0 | 0 |

All 31 predate this task. Nothing was backfilled. The rows remain valid: the new
`--reason` requirement is enforced on the *transition*, not as a node-level schema
constraint, so existing terminal rows are untouched and unbroken.

---

## 2. Other premises the live state contradicted

1. **Baseline test count.** The task file says "memory says 341; verify"; my brief
   said 697. Neither is live. Immediately before my first edit the suite was
   **746 collected (743 passed, 3 failed)** — and other lanes were landing tests
   concurrently throughout, so even that is a moving number. See §6.

2. **`withdrawn` reachability was widened beyond the task file's list.** The task
   file (§4 C2) lists `withdrawn` as reachable from `proposed`, `accepted`,
   `in_progress`. The integrator's `research.yaml` also made it reachable from
   `blocked`, matching how `superseded` already behaved there. **Reporting the
   widening, not reconciling it silently.** It is the right call — a blocked task
   whose premise turns out false must be withdrawable without first being un-blocked —
   but it is a deviation from the written spec.

3. **`seldon_task_create(blocks=...)` was dead on arrival.** The MCP tool called
   `create_link()` without the required `from_type`/`to_type` arguments, which would
   raise `TypeError` on every invocation with a `blocks` target. Nothing exercised
   it. Fixed in this lane (it is my file) and covered by
   `test_mcp_create_with_blocks_writes_the_edge`.

4. **`updated_at` is null on the ai-readiness-kg superseded nodes.** Cosmetic,
   pre-dates the `transition_state` change that sets it. Noted, not acted on.

---

## 3. What shipped

### `seldon/core/artifacts.py` (owned exclusively; other lanes call it)

Named constants, with comments, replacing what would otherwise be magic strings:
`CLAIM_TRANSITION = ("accepted", "in_progress")`,
`REASON_REQUIRED_STATES = ("withdrawn", "superseded")`, `SUPERSEDED_BY_REL`.

New public functions (all with Args/Returns/Raises docstrings):

- `terminal_states(domain_config, artifact_type)` — states with no successors.
  **Derived from the state machine, never enumerated in code**, so a terminal state
  added to `research.yaml` needs no code change.
- `open_states(domain_config, artifact_type)` — states in which live work is still
  possible: not terminal, **and** with at least one non-terminal successor. For
  `ResearchTask` this derives exactly `{proposed, accepted, in_progress, blocked}`
  and excludes `completed`, whose only successor (`verified`) is terminal. This
  replaces the two hardcoded `OPEN_STATES` lists that existed in `task.py` and
  `mcp_server.py`.
- `resolve_artifact_id(driver, database, id_prefix)` — pure (non-`click`) full-or-prefix
  resolver raising `ValueError` with the candidate list on ambiguity. The CLI needed
  this: the integration pass closes tasks by 8-char prefix, which
  `seldon task update` could not previously do (it passed the prefix straight to an
  exact-match `get_artifact` and reported "not found").
- `transition_task(...)` — the single ResearchTask-aware transition. Wraps
  `transition_state` with the two behaviours the plain state machine cannot express:
  the claim marker and the reason-bearing terminals. **Every precondition is checked
  before the first event is appended**, so a rejected call leaves no trace in the
  event store or the graph — verified by tests that snapshot the event list either
  side of a rejected call.

`walk_to_completed` now routes each step through `transition_task`, so a close walk
that crosses `accepted → in_progress` records the closer as claimant. It gained a
`claimed_by` parameter and a full docstring.

### C2 — terminal states

- `withdrawn` and `superseded` both require a non-blank reason, stored as
  `terminal_reason` via an `update_artifact` event written **before** the
  `artifact_state_changed` event. A blank/whitespace/absent reason is a hard
  `ValueError` with no state change and no events.
- `superseded` accepts an optional `--superseded-by ARTIFACT_ID` (full id or
  prefix). The target is resolved, confirmed to exist, and its type validated
  against the `superseded_by` edge's declared endpoints before anything is written;
  the edge is then created after the transition. An unknown id, an ambiguous prefix,
  or an illegal endpoint type (e.g. a `Citation`) is a hard error with **no state
  change**.
- Passing a reason to a non-terminal transition, `--superseded-by` to a
  non-superseding transition, or `--claimed-by` to a non-claim transition are all
  hard errors rather than silent drops.
- No backfill of existing rows. See §1.

### C3 — CLI/MCP parity

- **`seldon task close <id> [--note]`** — new. Calls
  `artifacts.walk_to_completed`, the *same function* MCP `seldon_task_close` now
  calls. `mcp_server._walk_task_to_completed` is reduced to a five-line adapter that
  supplies `actor="desktop"`; the duplicate walker it used to contain is deleted.
  There is exactly one walker in the codebase.
- **`seldon task withdraw <id> --reason`** and
  **`seldon task supersede <id> --reason [--superseded-by]`** — new.
- **`seldon task update`** gained `--reason`, `--superseded-by` and `--claimed-by`,
  and now resolves id prefixes.
- **MCP shape choice: two new verb tools, `seldon_task_withdraw` and
  `seldon_task_supersede`, rather than extending `seldon_task_update`.**
  *Reason:* the established MCP pattern in this file is verb-per-tool —
  `seldon_task_close` already exists as its own tool even though it is expressible
  as repeated `seldon_task_update` calls, and `seldon_issue_create`/`seldon_issue_update`
  follow the same shape. A tool's docstring is its contract for a Desktop model, and
  "reason is required, and here is what `superseded_by` accepts" is far more legible
  on a dedicated tool than as conditional prose inside a generic updater. Extending
  `seldon_task_update` would also have meant either overloading its existing `note`
  argument (which is echoed, not stored) or adding a second, silently-ignored-most-of-
  the-time `reason` argument.
  Consequence: **`seldon_task_update` now refuses `withdrawn` and `superseded`** with
  an error pointing at the two dedicated tools. This is a deliberate behavior change —
  the 8 `desktop`-actor supersedes in ai-readiness-kg came through
  `seldon_task_update`, and that route can no longer drop a reason on the floor.
  `seldon_task_update` also now returns `Error: ...` strings for invalid transitions
  instead of raising out of the tool.

### C4 — claim marker

- `accepted → in_progress` records `claimed_by` (defaults to the actor: `human` from
  CLI, `desktop` from MCP; override with `--claimed-by`) and `claimed_at` (ISO-8601,
  aware UTC).
- `seldon task list` shows a `CLAIM` column (`agent@timestamp`) for `in_progress`
  rows; `seldon_task_list` appends `(claimed by X at T)` and, in `brief=False` mode,
  also surfaces `terminal_reason`.
- **`seldon task list --stale-claims HOURS`** — HOURS is a required caller argument
  with no default anywhere in the code. Lists `in_progress` tasks whose `claimed_at`
  is older than the cutoff, prints `Report only — no task has been transitioned or
  released`, and separately counts `in_progress` tasks carrying no claim marker at
  all (which cannot be aged and are never guessed at). **No automatic transition, no
  auto-release**, asserted by a test that re-reads both tasks' states afterwards.

### C5 — tests

New file `tests/test_task_lifecycle.py`, **50 tests**, plus one repaired assertion in
`tests/test_state.py`. Coverage:

- **The whole transition matrix in one sweep.** `test_matrix_permits_exactly_what_the
  _config_declares` iterates every (from, to) pair of the 9 declared states — 81
  pairs — and asserts each is accepted iff `research.yaml` declares it, checking the
  stored state after both the allowed and the forbidden case. Reads the matrix from
  the config, so a future state change exercises it without editing the test.
- `withdrawn`/`superseded` unreachable from `completed` **and** `verified`
  (parametrized 2×2).
- Nothing reachable out of `withdrawn`/`superseded` — every state probed as a target.
- Missing reason (`None`, `""`, `"   "`) × both terminals: hard error, state
  unchanged, **event list byte-identical to before the call**.
- `superseded_by` edge creation (by full id and by prefix); failure paths for unknown
  id and illegal endpoint type, each asserting no state change *and* no events.
- **`test_cli_close_walk_emits_the_same_events_as_the_mcp_close_walk`** — parametrized
  over all four legal starting states. Asserts on the event store, comparing the
  `(event_type, from_state, to_state)` sequence emitted by `seldon task close` against
  the one emitted by `mcp_server._walk_task_to_completed`. `actor` is asserted
  separately (`human` vs `desktop`) because it differs by surface on purpose.
- Claim fields set and defaulted; refused on non-claim transitions; surfaced by both
  `seldon task list` and `seldon_task_list`.
- Stale-claim report: old claim listed, fresh claim not, both still `in_progress`
  afterwards; unmarked `in_progress` tasks counted not aged.
- CLI: default view hides terminal states *and* `completed`, `--all` restores them;
  unknown id and ambiguous prefix are hard errors.
- Regression test for the `seldon_task_create(blocks=...)` crash.

---

## 4. `seldon task list` — the default-behavior change, stated plainly

| surface | OLD default | NEW default |
|---|---|---|
| `seldon task list` (no flags) | **every task in every state** | open states only: `proposed`, `accepted`, `in_progress`, `blocked` |
| `seldon task list --open` | open states (hardcoded list) | unchanged in effect; now derived from config, kept as an explicit alias of the default |
| `seldon task list --all` | did not exist | every task in every state (the old default) |
| `seldon_task_list()` | `state_filter="open"`, hardcoded list | `state_filter="open"`, list derived from config — **no behavior change** |
| `seldon_task_list(state_filter="completed")` | Cypher literal interpolation | parameterised; same results |

**This is a breaking change for any existing caller of bare `seldon task list` that
expected to see completed or terminal tasks.** Anything that parsed the full listing
must now pass `--all`. The `--state` filter is unchanged and still reaches any single
state, including terminal ones. `--state`, `--open`, `--all` and `--stale-claims` are
mutually exclusive, with a hard error if more than one is given.

The default set is derived, not enumerated: `open_states()` computes it from
`research.yaml`. Adding a terminal state to the config removes it from the default
view with no code change. Note the derived set excludes `completed` as well as the
four terminal states — `completed` is not terminal (it can reach `verified`) but its
only successor is, so no live work remains. This is a *superset* of what §4 C3
required ("exclude terminal states by default") and was chosen so the CLI default
matches the MCP default exactly, which was the parity point of the requirement.

---

## 5. Deferred, and why

- **No backfill of `terminal_reason` on the 31 ai-readiness-kg rows.** Explicitly
  out of scope per §4 C2. Counted and reported instead (§1).
- **No auto-release of stale claims.** Explicitly out of scope per §4 C4. The report
  says so in its own output.
- **`note` on `seldon task close` / `seldon_task_close` is still echoed, not stored.**
  Unchanged from today. Storing it would need a `close_note` property in
  `research.yaml`, which is read-only for this lane. `terminal_reason` is the
  property that exists and it is reserved for the two states that genuinely need it.
- **The 7 misparsed descriptions** among the superseded rows — Lane D's file.
- **No AD-028 document written.** `research.yaml` and my code reference "AD-028" in
  comments and docstrings because the integrator's schema edit introduced that
  reference. The AD document itself does not exist yet. See below.

---

## 6. Test results

Command (the mandatory form):

```
python -m dotenv -f .env run -- python -m pytest tests/ -v
```

### Final count

```
python -m dotenv -f .env run -- python -m pytest tests/ -q \
    --deselect tests/test_init.py::TestInitWritesADerivedOntologySource
```

**928 passed, 0 failed, 6 deselected.** Reproduced twice, back to back.

**The whole suite is green.** The 6 deselected tests are one class in Lane D's
`tests/test_init.py` which, as written, breaks every Neo4j test that runs after it —
root cause and fix in §6.1 below. Undeselected, the same suite reports **18 failed /
916 passed** (also reproduced three times), and every one of those 18 failures is a
downstream casualty of that class, not a defect in the code under test.

Lane C's own files are green in every configuration:

| selection | result |
|---|---|
| `tests/test_task_lifecycle.py` | **50 passed** (reproduced) |
| `test_task_lifecycle.py` + `test_task.py` + `test_state.py` + `test_mcp_tools.py` | **75 collected, all passing** |
| `test_task_lifecycle.py` + `test_mcp_tools.py` | **59 passed** |

An earlier run also showed two failures in `tests/test_docs_check.py`
(`test_docs_check_required_vs_doc_stats`, `test_docs_check_mixed_completeness`), both
asserting `doc_total == 2` for `Result` and getting `3` because `research.yaml` gained
a `name` property on `Result` without a `category` key. Another lane resolved that
during the session; it is green in the final runs above. Recorded because it was a
real, if transient, cross-lane collision.

### 6.1 Root cause of the 18 failures — `tests/test_init.py` poisons Neo4j auth

**This is a real, deterministic, reproducible defect introduced by this sweep, and it
is not mine to fix — `tests/test_init.py` and `seldon/commands/init.py` are Lane D's.
It must be fixed before the integration pass, or the suite can never be green.**

`TestInitWritesADerivedOntologySource._run_init` does:

```python
monkeypatch.setenv("NEO4J_PASSWORD", "wrong-on-purpose-for-this-test")
runner.invoke(init_command, [name])
```

`seldon init` then opens a real connection to the live Neo4j server with deliberately
wrong credentials. Six tests in that class call it. Neo4j counts consecutive failed
authentications per client and trips
`Neo.ClientError.Security.AuthenticationRateLimit` — **"The client has provided
incorrect authentication details too many times in a row."** From that moment, for
the duration of the lockout window, **every** connection to that server is refused,
including correctly-authenticated ones, from that process *and any other*.

Decisive experiment:

```
$ pytest tests/test_init.py -q
40 passed in 0.98s                     # the file itself is green

$ python -c "<connect with the correct password from .env>"
AUTH BLOCKED: ClientError {neo4j_code: Neo.ClientError.Security.AuthenticationRateLimit}
```

The file passes and leaves the server refusing everyone. Bisecting the suite
(`test_init.py` + `test_mcp_tools.py` → 8 failed; every other single file +
`test_mcp_tools.py` → all passed) names `test_init.py` unambiguously. Because
pytest collects alphabetically, `test_init.py` runs early, so `test_mcp_tools.py`,
`test_numbering.py`, `test_ontology.py`, `test_session_commands.py`,
`test_task_lifecycle.py` and others all take the hit — which is exactly why the
failing set looked so unstable (18 → 24 → 38 → 41 → 51 → **409 errors**): the lockout
window is time-based, so how many later files land inside it depends on timing.

**Recommended fix (Lane D):** exercise the "setup warns, `seldon.yaml` is still
written" path without ever presenting bad credentials to the live server — point the
URI at a dead port instead of corrupting the password, e.g.

```python
monkeypatch.setenv("NEO4J_URI", "bolt://127.0.0.1:1")
```

That yields a connection failure rather than an authentication failure, tests the same
branch, and touches no rate limiter. (Monkeypatching the driver factory to raise would
work equally well.)

**Correction to an earlier conclusion in this document.** Before finding this, I
attributed the instability to cross-lane contention on the shared `seldon-test`
database. Contention was *also* real and directly observed (see §6.2), but it is not
the dominant cause; this is. Recording the correction rather than quietly replacing
the earlier text, because "no stable number available" was a claim I made and it was
wrong.

### 6.2 Secondary finding: cross-lane contention on `seldon-test` (real, but not the cause)

**Baseline caveat.** Neither "341" (task file) nor "697" (lane brief) matched live
state. Immediately before my first edit: **743 passed, 3 failed, 746 collected** —
the 3rd failure being `test_state.py::test_invalid_state_transition_carries_valid_
options`, which the integrator's `withdrawn` addition broke and which I repaired
(rewritten to assert against the config's declared successor set rather than a frozen
literal list, so the next state addition does not break it for the wrong reason).
Other lanes landed tests concurrently throughout, so the 746 → 934 delta is not mine
alone; **my contribution is +50 new tests and 1 repaired assertion.**

All four lanes share one Neo4j instance and one `seldon-test` database, whose
`clean_test_db` fixture runs `MATCH (n) DETACH DELETE n` before each test. With lanes
running concurrently, one lane's wipe deletes another lane's fixture nodes mid-query,
producing `Neo.ClientError.Statement.EntityNotFound: Unable to load NODE ...` — a node
deleted between the query plan and the read, which single-threaded pytest cannot do to
itself.

Directly observed: `ps -eo pid,command` during one of my runs showed
`PID 80965  python -m pytest tests/test_result_registry.py` — Lane A's suite — running
against the same database. Sampling `SHOW TRANSACTIONS` on `seldon-test` during a run
caught a `MATCH (n) DETACH DELETE n` from one client address interleaved with
`MATCH (a:Artifact {artifact_id: $id}) SET a.state = $state` from another.

This is real but secondary: the final green runs in §6 were obtained with lanes still
active, so it is survivable. It remains a latent harness defect worth fixing —
`TEST_DATABASE` in `tests/conftest.py` is a hardcoded constant (`"seldon-test"`), so
concurrent runs cannot be isolated. Deriving it from an env var with `seldon-test` as
the default would make the harness safe for exactly the multi-lane execution model the
task file prescribes in §1. `tests/conftest.py` is outside every lane's declared file
set, so it is recorded here rather than changed.

---

## 7. Cross-lane needs (for the integration pass)

1. **`seldon/commands/go.py`** (Lane D) lists the available MCP tools at lines ~29 and
   ~93. It does not know about `seldon_task_withdraw` or `seldon_task_supersede`, and
   still describes `seldon_task_update` as the way to do a single transition without
   the new refusal. Needs a two-line update.
2. **`CLAUDE.md`** (integrator) — the "MCP Tools" table needs `seldon_task_withdraw`
   and `seldon_task_supersede` rows, and the CLI skills table should gain
   `task close` / `task withdraw` / `task supersede`.
3. **AD-028 does not exist as a document.** `research.yaml`'s new comments and every
   docstring I wrote reference it. Per §7 of the task file the RESULT must confirm a
   dated design-decision entry for terminal-state semantics and claim-marker
   semantics; that entry should be written as AD-028 covering, at minimum:
   `withdrawn` vs `superseded` semantics, the reason requirement, the
   `superseded_by` edge direction (inverse of `supersedes`, authored on the losing
   side), and the claim marker being advisory-and-reported-only.
4. **BLOCKING — `tests/test_init.py::TestInitWritesADerivedOntologySource` trips
   Neo4j's authentication rate limiter and breaks every Neo4j test that runs after
   it.** Lane D's file. Full diagnosis, decisive experiment and one-line fix in §6.1.
   **The suite cannot go green until this is fixed.** With those 6 tests deselected
   the suite is 928 passed / 0 failed; with them in, 18 unrelated tests fail.
4b. **`tests/conftest.py`: `TEST_DATABASE` is a hardcoded constant.** Making it
   env-overridable would let the four-lane execution model in §1 of the task file
   actually work. Outside every lane's file set — see §6.2.
4c. **`seldon cc complete` now records a claim.** `seldon/commands/cc.py` (Lane D)
   calls `walk_to_completed(actor="cc")` in two places. Because the walk now routes
   through `transition_task`, a CC task walked from `proposed` records
   `claimed_by="cc"` and `claimed_at` as it crosses `accepted → in_progress`. The
   signature change is backward-compatible (a new optional `claimed_by` kwarg);
   the extra `artifact_updated` event is the only behavioural difference. Flagged so
   Lane D is not surprised by it.
5. **Reinstall the CLI** before the integration pass closes tasks with
   `seldon task close`. Verified working from this checkout
   (`seldon task --help` lists close/withdraw/supersede), but §6 step 4 of the task
   file should confirm the install path for other projects.
6. **`seldon task close` prefix support is new.** The integration pass closes six
   tasks by 8-char prefix; that now works. Before this lane,
   `seldon task update <prefix>` reported "not found" for anything but a full UUID.

---

## 8. Files changed

| File | Change |
|---|---|
| `seldon/core/artifacts.py` | +3 constants, +4 public functions (`terminal_states`, `open_states`, `resolve_artifact_id`, `transition_task`), `walk_to_completed` routed through `transition_task` and documented |
| `seldon/commands/task.py` | module docstring; `list` rewritten (default change, `--all`, `--stale-claims`, claim column); `update` gains `--reason`/`--superseded-by`/`--claimed-by` and prefix resolution; new `close`, `withdraw`, `supersede`; shared `_open_project`/`_load_task`/`_terminal_transition`/`_parse_claimed_at` helpers |
| `seldon/mcp_server.py` | `MCP_ACTOR` constant; `_walk_task_to_completed` reduced to an adapter over the shared walker; `seldon_task_update` refuses reason-bearing states and returns errors instead of raising; new `seldon_task_withdraw` and `seldon_task_supersede` via shared `_mcp_terminal_transition`; `seldon_task_list` uses derived open set, parameterised Cypher, surfaces claims and reasons; `seldon_task_create(blocks=...)` `TypeError` fixed |
| `tests/test_task_lifecycle.py` | **new** — 50 tests |
| `tests/test_state.py` | one assertion repaired to be config-derived rather than a frozen literal |

Not committed, per instructions. `seldon verify` not run, per instructions. No Seldon
tasks closed, per instructions.
