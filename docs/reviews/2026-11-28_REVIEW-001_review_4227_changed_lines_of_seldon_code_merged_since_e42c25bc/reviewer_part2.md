# Reviewer report, part2 (/tmp/qz_delta/part2.diff), as returned to REVIEW-001

# Review: seldon worktree `magical-plotting-cake`, delta `/tmp/qz_delta/part2.diff`

**Suite and lint:** not run, as the brief instructed (another session runs the suite). The only things executed were read-only greps and one probe script outside the repository (`/tmp/qz_probe/probe_guard.py`), which calls `controls.refusal` directly. Its output is quoted in L3-1.

## Removed or changed guard lines, and what guards each one now

| Removed or changed line (diff) | What it guarded | What guards it in the snapshot |
|---|---|---|
| `cross_project.py` `resolve_after_refs(..., [target.ref])` | A cross-graph `After:` wait | Strengthened: `refuse_filings=True` at `seldon/core/cross_project.py:222` |
| `decisions.py` `repos[name] = (root / rel)` for every entry | Where each register lives | `decisions.py:886` now silently skips an entry that names this repository. Nothing reports the skipped entry. |
| `decisions.py` `u.records(repo)` in `project()` | Register verification before projection | Still there: `Register.events()` runs `verify()`, including `_verify_pending`, at `decisions.py:593-598` |
| `dispatch.py` old `plan_launches` (exclusive and `touches_overlap` checks for every row) | Exclusive tasks and shared-resource overlap | For lane rows nothing guards it at plan time (`dispatch.py:672-680`). The only guard is the merge round's `outside_writes` (`commands/dispatch_worktree.py:1234-1245`). Resource overlap is never checked for a lane task (L1-2). |
| `dispatch.py` `STUCK_AFTER_PASSES_BY_CRITERION_UNLESS_NAMED = {"api_key_present": 1}` | The `environment_in_flight` alarm fired at `stuck_after_passes` | Weakened: 12 passes for every consumer that does not name the key (`dispatch.py:761-763`) (L7-3) |
| `gate_plan.py` `CALL_SITES` tuple | Allow-list of call sites | Widened by `scheduled`. Still enforced in `record_payload` (`gate_plan.py:~697`). |
| `gate_plan.py` `last_failed_files` over all runs | R31: last-failed files run in the next gate | Scheduled runs are excluded. Their failures are guarded instead by the closure at `commands/dispatch_worktree.py:1146,1227,1264,1274` and `commands/gate.py:70`. |
| `gate_plan.py` `cadence_due` block inside `plan()` | A periodic full run, whoever called the gate | Partly replaced by `scheduled_due` (`gate_plan.py:381`), which is reached only from dispatcher passes (`commands/dispatch.py:1566`, `commands/dispatch_worktree.py:292`). Nothing replaces it when no pass runs (L1-3). |
| `hooks.py` `--local core.hooksPath` check and set | The tracked hook runs in each checkout | Replaced by `_point_both` (`hooks.py:353`), plus the new local-scope problem in `status()` (`hooks.py:396`). Preserved. |
| `project_new.py` `need` tuple | Required kit keys | Widened (stricter) |
| `requirements.py` `AUTHORED` | Allow-list of fields a person authors | Widened by four disposition fields. Values are checked by `DISPOSITIONS` and `check_disposition` (`requirements.py:~380, ~396`). |
| `returns.py` `latest_open` query | Which open task a return waits on | Strengthened: filings and FUTURE tasks are excluded |
| `stations.py` `part_criteria` (Acceptance-only reading) | Which `check:` lines the Stop gate runs | Widened to bare marked lines, with dedupe. Fenced blocks are still excluded (`stations.py:~347`). |
| `worktree.py` `if not src.exists() or dst.exists() or dst.is_symlink(): continue` | Never overwrite a worktree path with a link | Same conditions, now reported (`worktree.py:link_report`). Preserved. |
| `gate_plan.py` `for key in ("full_every_s",)` | Positive-seconds check | Extended to `full_overdue_s`. The new `scheduled_worktree` check is too weak (L2-1). |

---

## Lens 1: Scope and invariants

- **ID:** L1-1
- **Severity:** major
- **Location:** `seldon/core/returns.py:484-490`
- **Evidence:**
  ```
  if HEADER_NOTHING not in headers:
      # ... a Stop gate that ran no check is no evidence (AD-034-R26). The RESULT is what a return's session owes; its presence is the check.
      out += ["## Part A: apply it", "", "Acceptance:",
              f"- `check: test -f cc_tasks/{task_file_stem}_RESULT.md` ..."]
  ```
- **Why it matters:** The finish already requires a committed RESULT. This check therefore always passes, and `gate_evidence` (`commands/dispatch_worktree.py:916`) counts a passing Stop gate with at least one check as merge evidence. A return's code changes in a project with no gate command now merge on a tautology. That is the exact case R26 exists to refuse.
- **Fix:** Remove the generated check. A return to a project with no `gate_command` should stay `merge_blocked: ungated`, or the return template should require a substantive check written by the producer. Exclude `test -f <own RESULT>` from what counts as evidence in `gate_evidence`.

- **ID:** L1-2
- **Severity:** minor
- **Location:** `seldon/core/dispatch.py:663-680`
- **Evidence:**
  ```
  if lane:
      lane_running = [r["task_id"] for r in running if r.get("lane")]
      running = [r for r in running if not r.get("lane")]
  ...
  if lane and cand.get("lane"):
      if len(lane_running) < lane["slots"]: launch.append(...)
      continue
  ```
- **Why it matters:** AD-038-R40 exempts a lane task only from exclusive holds. The code also drops `touches_overlap` both ways: a lane candidate never checks the resources it declares, and running lane rows are removed from `held`, so they hold nothing for non-lane candidates.
- **Fix:** Keep the exclusive exemption. Run `touches_overlap` for lane candidates against every running row, and keep running lane rows in the resource-overlap set (not in the slot count).

- **ID:** L1-3
- **Severity:** minor
- **Location:** `seldon/core/gate_plan.py:543` (cadence removed); `seldon/commands/dispatch_gate.py:161-170`
- **Evidence:** `# SEL-055 (AD-034-R38): no cadence here.` `maybe_run` is called only from the dispatcher passes (`commands/dispatch.py:1566`, `commands/dispatch_worktree.py:292`).
- **Why it matters:** A project with slices whose dispatcher is disabled, stopped or stuck now never runs the full suite. Nothing reports how old the newest full gate is; `go.py:930` prints the cadence, not the age. The periodic reference run (Fowler's) is now conditional on the dispatcher.
- **Fix:** Have `seldon verify` and `seldon go` warn when `scheduled_due(..., idle=True)` returns a reason, so the run's age is visible without a pass.

- **ID:** L1-4
- **Severity:** minor
- **Location:** `seldon/core/gate_plan.py:739-749` (`completion_evidence`), `seldon/core/gate_plan.py:730-736`
- **Evidence:** `return passing_record(events, out.stdout.strip())`. `passing_record` accepts any passing clean `gate_run`, scoped or inert.
- **Why it matters:** AD-034-R41 names "a scheduled run, `seldon gate main`, or a full `seldon gate run`". The code also accepts a scoped run, including a `tests: none` inert plan. Nor does it check that the blocked task's branch is on main.
- **Fix:** Filter to `tier == "full"` or `call_site == "scheduled"`. Also require that the task's dispatch branch tip be an ancestor of main (`git merge-base --is-ancestor`), or record its absence on the completion.

- **ID:** L1-5
- **Severity:** minor
- **Location:** `seldon/core/gate_plan.py:341-354, 423-431`
- **Evidence:**
  ```
  if src == "gate_run": return ev.get("tier") == TIER_FULL
  return src == "gate_record"
  ...
  if src in ("gate_record", "regate", "merge_gate"): return True
  ```
- **Why it matters:** In a project that declares both slices and a `gate_record`, the declared pass record is always admitted under closure. Any merge on a pass record also clears main red, even one scoped by `tree_paths`. R39 says the closure ends only on "a passing full gate of its tip", and the record's command does not apply the closure.
- **Fix:** In `_merged_on_full_pass`, count `gate_record` only when the record has no `tree_paths` scope. In `closure_admits`, admit `gate_record` only together with a closure plan of the red files. Alternatively, refuse that config combination at load until it is designed.

## Lens 2: Correctness

- **ID:** L2-1
- **Severity:** major
- **Location:** `seldon/core/gate_plan.py:187-192`; `seldon/commands/dispatch_gate.py:48-55, 70`
- **Evidence:**
  ```
  _relative([sw], "dispatch.gate.scheduled_worktree")   # refuses only "/..." and ".."
  ...
  if wt.exists() or wt.is_symlink(): WT.remove(project_dir, wt)
  if wt.exists(): shutil.rmtree(wt)
  ```
- **Why it matters:** `scheduled_worktree: "."` or `"docs"` passes validation. `WT.remove` fails on a path that is not a worktree, and then `rmtree` deletes the primary checkout or a tracked directory. The comment "it is this module's own scratch path, never a task's" is not enforced anywhere.
- **Fix:** At load, require the path to sit under an ignored directory (`git check-ignore`) and to name no tracked path. In `_clear`, call `rmtree` only when `git worktree list --porcelain` lists `wt`, or when `wt` holds the module's own marker file.

- **ID:** L2-2
- **Severity:** minor
- **Location:** `seldon/core/recall.py:855`
- **Evidence:** `need = sel["lexical_min_shared_terms"].get("issue")` (stage 4, dead ends of kind `worktree_kept`/`superseded`)
- **Why it matters:** The docstring says the threshold is "of its kind", and seldon.yaml sets those kinds to `null` (no lexical hit). The code borrows the Issue threshold of 8 instead, so dead ends get through on shared words when the config says they should not.
- **Fix:** `.get(c.kind)`.

- **ID:** L2-3
- **Severity:** minor
- **Location:** `seldon/core/recall_audit.py:552`
- **Evidence:** `landed[c.id] = f.stat().st_mtime if f.is_file() else 0.0`
- **Why it matters:** An mtime is when the checkout last wrote the file, not when the RESULT reached main. After a fresh clone or a rebase, every RESULT looks newer than every launch, `pool_then` is empty, and the replay reports nothing without saying why.
- **Fix:** Use the commit time of the file's first addition: `git log --diff-filter=A --format=%ct -1 -- <path>`.

- **ID:** L2-4
- **Severity:** minor
- **Location:** `seldon/core/recall_audit.py:538, 556`
- **Evidence:** `digest = hashlib.sha256(json.dumps(new_selection ...))`, `key = f"{name}:{sess.stem}:{digest}"`
- **Why it matters:** The checkpoint key leaves out `recall_block` (`top_n`, `bm25`, `min_shared_terms`), which decides both the OLD and NEW sides. A changed block resumes stale rows silently, against constitution §15.2.
- **Fix:** Hash `recall_block` and `new_selection` together into the key.

## Lens 3: Security and egress

- **ID:** L3-1
- **Severity:** major
- **Location:** `seldon/core/controls.py:112-136` (`refusal`), `_PATH_KEYS`/`_TEXT_KEYS` at `:57-59`
- **Evidence:** The probe, with `~/.ssh` as the deny path:
  ```
  read_canonical refused
  read_upper     ALLOWED   (Read ~/.SSH/id_rsa; APFS realpath keeps the case: /Users/brock/.SSH)
  bash_rel       ALLOWED   (cd && cat .ssh/id_rsa)
  bash_upper     ALLOWED
  bash_glob      ALLOWED   (cat ~/.ss?/id_rsa)
  bash_home_cwd  ALLOWED   (cat .ssh/id_rsa, cwd=$HOME)
  grep_parent    ALLOWED   (Grep path=$HOME reads inside the guarded directory)
  ```
- **Why it matters:** R44 claims the guard stops "a session's ordinary reach". A cwd-relative path, a case variant on a case-insensitive volume, and a Grep of the parent directory are all ordinary reach. The guard sits in front of the Hive minter's secrets (`seldon.yaml:416`).
- **Fix:** Use an OS-enforced deny instead of string matching: Claude Code's sandbox filesystem deny rules for Bash plus `Read(//abs/path/**)` deny rules, or run sessions as a separate Unix user. If the hook stays, compare paths case-folded on case-insensitive volumes, refuse a search whose root is an ancestor of a deny path, and resolve relative tokens in Bash against `cwd`.

- **ID:** L3-2
- **Severity:** major
- **Location:** `seldon/core/controls.py:225-232`; `seldon/commands/dispatch.py:2721`
- **Evidence:** `limits_spec` covers only `{"hook_command", "deny_paths", "spend_ceiling_factor"}`. Controls run again only `if state.get("fingerprint") != fp`.
- **Why it matters:** The hook command is `sys.executable -P -m seldon ...`, which does not change when seldon's code changes. An upgrade that breaks `refusal` or `stations.inspect` keeps the old "held" verdict indefinitely, which is the "limit nobody has tried" case R45 exists to end. The plants also try only the canonical spelling (`:157-158`), so L3-1 cannot fail its control.
- **Fix:** Add the installed seldon version or the commit of `controls.py`/`stations.py` to the spec. Add plants for a relative path from the deny path's parent, a case-variant spelling, and a Grep of the parent directory.

- **ID:** L3-3
- **Severity:** minor
- **Location:** `seldon/core/hive.py:101-103`
- **Evidence:** `"error": f"exit {proc.returncode}: {(proc.stderr or '').strip()[-300:]}"`, which is written into the `session_identity` event and pushed.
- **Why it matters:** The comment assumes only stdout can carry a token. A minter that echoes a credential in a stderr traceback publishes it in the event store.
- **Fix:** Run the stderr tail through the secret scanner (`squiddy.secret_scan` or `filing`'s scan) before recording it, or record only the exit code and line count.

## Lens 4: Tests

- **ID:** L4-1
- **Severity:** major
- **Location:** `tests/test_sel054_identity_and_controls.py:153-178`
- **Evidence:** The parametrized refusal cases use canonical, `~/` and `{s}/../` spellings. No case uses a cwd-relative path, a case variant, a glob or an ancestor search root.
- **Why it matters:** The suite proves the guard catches the spellings it was written for, not that it holds against ordinary reach (L3-1).
- **Fix:** Add failing-first tests for each ALLOWED row of the L3-1 probe.

Also missing:
- A test that `scheduled_worktree: "."` or a tracked directory is refused at load (L2-1).
- A test that a code change re-runs the controls (L3-2).
- A test that a return's generated check is not counted as evidence (L1-1).
- A test of `completion_evidence` with a scoped record (L1-4).

## Lens 5: Provenance and evidence

- **ID:** L5-1
- **Severity:** minor
- **Location:** `seldon/core/decisions.py:1880-1905`
- **Evidence:** `MATCH (t:Artifact)-[:CONSTRAINED_BY]->(d:Artifact:Decision) WHERE d.state <> 'accepted'`, and `verify --fix` then removes each edge.
- **Why it matters:** The prune also ends edges to `proposed` records, and edges from completed tasks to records superseded later. The second case erases the trace of what bound the task when it ran. The projection also now leaves pending acceptances out (`:1803-1812`), so `--fix` run in a worktree can end an edge to a record the branch has just accepted, in the shared graph.
- **Fix:** Limit the prune to tasks in open states, and to Decisions whose register status (not the projected state, which ignores pending records) is not accepted. Leave edges from terminal tasks in place as history.

## Lens 6: Adopter readiness

- **ID:** L6-1
- **Severity:** major
- **Location:** `seldon.yaml:107`; `seldon/core/prior_art.py:378-386`
- **Evidence:** `internal_roots_from: ../factory/seldon.yaml#portfolio.repositories`, and `raise PriorArtError(f"... names {target}, which does not exist")`
- **Why it matters:** `prior_art.settings` sits on the commit-msg hook, `seldon verify` and `cc register` paths, for seldon and every consumer that references its block. A clone without a sibling `factory` checkout cannot pass the prior-art gate.
- **Fix:** Treat a missing portfolio file as a reported, degraded search (a note in the receipt, roots from `internal_roots` only), not a settings error. Or make the key per machine (env or kit-local config).

- **ID:** L6-2
- **Severity:** minor
- **Location:** `seldon.yaml:414-416`
- **Evidence:** `mint_command: /opt/anaconda3/bin/python /Users/brock/GitHub/factory/scripts/hive.py mint`
- **Why it matters:** Absolute paths for one user and one machine, in a tracked config that the kit copies into consumers. Any other machine fails the mint on every launch (recorded, not fatal).
- **Fix:** Use paths relative to the kit (the `kit_relative` rule `project_new` already applies), or an env-provided interpreter.

## Lens 7: Brittleness

- **ID:** L7-1
- **Severity:** major
- **Location:** `seldon/core/controls.py` (whole module); `seldon/core/hive.py:1-25`
- **Evidence:** A denylist by substring and path prefix over tool inputs, with spellings added one incident at a time (`_spellings`: `~`, `$HOME`, `${HOME}`, `/private`).
- **Why it matters:** The root cause is that sessions run with the operator's full filesystem authority. Each new spelling is another per-incident patch.
- **Fix:** Use the known pattern: least privilege enforced below the agent. Options are an OS sandbox or a separate user, a secret delivered as a capability (the minted token only, which is already done), and the minter secret readable only by the dispatcher's user (Saltzer and Schroeder: least privilege, complete mediation).

- **ID:** L7-2
- **Severity:** minor
- **Location:** `seldon/core/hooks.py:353-388`
- **Evidence:** The shared `core.hooksPath` is set to the absolute value that the Claude Code CLI rewrites it to, "so the CLI finds nothing to change".
- **Why it matters:** The fix depends on undocumented behaviour of another tool, so its correctness rests on that tool's next release. It does use the right mechanism (per-worktree `config.worktree`).
- **Fix:** Keep the per-worktree value. Have `status()` treat the shared value as advisory, so that whatever the CLI writes cannot make a pointed checkout read "not installed". Keep `tests/test_sel052_hook_path.py` as the tripwire.

- **ID:** L7-3
- **Severity:** note
- **Location:** `seldon/core/dispatch.py:761-763`
- **Evidence:** `"environment_in_flight": ENVIRONMENT_WAIT_PASSES_DEFAULT` (12)
- **Why it matters:** This loosens an existing alarm from 3 passes to 12 for every consumer that does not name the key. The comment says it has no measured distribution.
- **Fix:** Record the change as a ruling erratum, and print the effective threshold in `seldon dispatch status`.

## Lens 8: Configuration keys

Every new key the diff adds (`held_alarm_after_s`, `held_repeat_s`, `gate.full_overdue_s`, `gate.scheduled_worktree`, `coordination_lane.*`, `premises`, `hive.*`, `guard.deny_paths`, `recall.selection.*`, `recall.audit.repositories_from`, `project_new.prior_art_baseline`, `project_new.projections`, `prior_art.internal_roots_from`) is read by code. No dead key was found. `scheduled_worktree` is read, but its validation is insufficient (L2-1).

---

## Synthesis

**Summary**
1. The delta adds a coordination lane, project premises, a minted session identity, planted controls, a full suite on main on a schedule with a red closure, recall's touch selection and its audit, project-new steps, a held alarm and a hooks-path repair.
2. Most removed guards are preserved or strengthened: register verification, link skips, `latest_open`, cross-graph filings.
3. Three removals have no full replacement: the per-plan cadence (L1-3), lane resource overlap (L1-2) and the `environment_in_flight` alarm threshold (L7-3).
4. The session guard is a string-matching denylist. It is bypassed by a relative path, a case variant, a glob and an ancestor Grep, all confirmed by probe (L3-1).
5. The planted controls cannot catch L3-1, and they never run again after a code upgrade (L3-2).
6. `scheduled_worktree` validation admits `.` or a tracked directory, which `_clear` then deletes with `rmtree` (L2-1).
7. Returns now carry a check that always passes, which counts as R26 evidence (L1-1).
8. Closure and completion evidence diverge from R39 and R41 for pass records and scoped runs (L1-4, L1-5).
9. The prior-art gate now hard-depends on a sibling `factory` checkout (L6-1).
10. The suite was not run here, by instruction.

**Fix first:** L2-1 (irreversible deletion), L3-1 with L3-2 (the secret guard and its control), L1-1 (an evidence tautology in the merge path).

**What the suite should add:**
- Guard bypass cases (each ALLOWED row of the L3-1 probe).
- Load-time refusal of `scheduled_worktree` values `.`, `docs` and `seldon`.
- A controls re-run on a code version change.
- `gate_evidence` refusing a return's `test -f RESULT` check as evidence.
- `completion_evidence` refusing a scoped record.
- `closure_admits` and `_merged_on_full_pass` with a `tree_paths`-scoped pass record.
- The stage-4 recall threshold read for the hit's own kind.

**Verdict.** The delta mostly does what AD-038 Addendum 16 and AD-034 Addendum 13 claim. The lane is confined at merge, premises and controls gate every launch path including the lane's (`_launch_gates` is called from `commands/dispatch.py:1607`, `commands/dispatch_worktree.py:306` and `commands/dispatch_lane.py:111`), and the scheduled run and closure are wired into the merge round and `seldon gate run`. Two claims do not hold as written. R44's "stops ordinary reach" fails against routine spellings. R45's "a limit nobody has tried is not known to work" is undone by a fingerprint that ignores the code doing the limiting. R39 and R41 are also looser in code than in their rulings. Separately, one config value (`scheduled_worktree`) can delete the repository. Until L2-1, L3-1/L3-2 and L1-1 are fixed, the safety properties this delta advertises are weaker than stated.
