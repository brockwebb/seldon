# AD-038: The machine reconciles its own state. The operator is not the retry loop.

Desktop session (squiddy thread SQ8, working in seldon), 2026-10-17. **Status: draft** until its prior-art verdict is recorded; commit under `draft:` (AD-036-R13). **Amends:** AD-036-R11 (per-writer commits), AD-037-R6 (where a station runs its check), the ResearchTask state machine in `seldon/domain/research.yaml`. **Governs:** FRICTION-001.

## 1. The condition, measured

Between 10 and 17 October the two standing dispatchers made 3,743 five-minute passes, launched 11 tasks, and refused 797 passes (`seldon/logs/seldon_dispatch.log`, `squiddy/logs/squiddy_dispatch.log`). Every clean-tree refusal (c7) was caused by a file the system itself wrote and did not commit. The longest stalls were 36 hours (seldon, one unregistered filing) and 19 hours (squiddy, four causes in turn). Seven tasks in eight days (PA-001, HOOK-001, DISP-c7, SEL-006, DESK-001, DESK-002, DESK-002R) each taught one more writer to commit itself, and each exposed the next writer.

The operator broke every stall by hand: a paste into Claude Code, a Desktop restart, or a re-issued task. Under the L4 model (`~/GitHub/CLAUDE.md`; icsp_notebook `CLAUDE.md`) none of those is an operator touchpoint. This is toil in the SRE sense: manual, repetitive, automatable, tactical, of no enduring value, and growing with the number of writers (Beyer et al., *Site Reliability Engineering*, ch. 5, "Eliminating Toil": the organization caps toil at 50% of time; this week it was close to 100% of the operator's time on these repos).

Five mechanisms produce the toil. Each is a design choice, not a bug:

1. **One global gate, many writers.** c7 computes one `git status` per pass and refuses the whole queue on any dirt (`seldon/core/dispatch.py:1166`, "c7 false for the WHOLE queue"). The dispatcher commits only lines whose actor is `dispatcher` or `desktop` (`core/dispatch.py:1081`); lines by `governed_sync`, `cc` and the prior-art writers are refused with "NOT committed", then counted as dirt. The gate punishes the system for its own writes.
2. **Blocked is terminal in practice.** `blocked` transitions only to `in_progress`, `superseded`, `withdrawn` (`research.yaml:1141`), and only `proposed` and `accepted` are dispatchable (`core/dispatch.py:460`). A false stop therefore costs a new task file, a supersede, and a re-registration (DESK-002 to DESK-002R).
3. **The MCP server refuses after any merge under `seldon/`.** `loaded_state.stale` compares the tree id of `HEAD:seldon` with what was imported; when they differ every tool returns `server_stale` and asks for a Desktop restart. Any task that merges Seldon code disables Desktop for the rest of the session. Reloading in place is not a fix: `importlib.reload` does not rebind names imported with `from ... import` or instances of old classes (Python docs, `importlib.reload` caveats), and the server imports that way.
4. **Stations inspect the wrong tree.** The milestone station runs a Part's `check:` in the primary checkout while an exclusive task works on a branch in a worktree (Issue `02d52bc4`). A correct session is halted.
5. **Premises are checked late.** Registration validates headers and criterion marks but runs no `check:` premise (`commands/cc.py:1140`); the first evaluation is at dispatch. A mistyped path (SQ-016) waits a day to be found.

## 2. Prior art

### External

- web receipt: url https://opengitops.dev/ | retrieved 2026-10-17
- web receipt: url https://sre.google/sre-book/eliminating-toil/ | retrieved 2026-10-17
- web receipt: url https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-dead-letter-queue-redrive.html | retrieved 2026-10-17
- web receipt: url https://docs.python.org/3/library/importlib.html | retrieved 2026-10-17

OpenGitOps principles v1.0.0: desired state is "versioned and immutable", and "software agents continuously observe actual system state and attempt to apply the desired state." A reconciler that finds drift repairs it; it does not stop the world and wait for a human. Seldon's dispatcher is a reconciler in every respect except this one: on dirt it refuses instead of reconciling.

Google SRE, "Eliminating Toil" (Rau, in Beyer et al. 2016): toil is "manual", "repetitive", "automatable", "tactical", has "no enduring value" and scales "linearly with service size". Each hand commit, restart and re-issue this week fits all six.

Amazon SQS dead-letter queue redrive: "move unconsumed messages from a dead-letter queue to another destination for processing. By default, dead-letter queue redrive moves messages from a dead-letter queue to a source queue." A halted task is a dead-lettered message; the queue needs a redrive, not a new message.

Python `importlib.reload` caveats: "Other references to the old objects (such as names external to the module) are not rebound to refer to the new objects"; "If a module imports objects from another module using `from … import …`, calling `reload()` for the other module does not redefine the objects imported from it." A long-lived in-process server cannot follow HEAD by reloading; it must run HEAD's code in a fresh process per call.

- library receipt: query "dispatcher reconciles uncommitted machine-written state before clean tree gate" | release library_graph_20261012_sq013_01_2026-10-12.json sha256:0989759c402ca41472806bdf9ab47529ba2eb5a6b25d0e75c1a6e29e650d4275 | rows lesson:2026-02-22_arXiv_2306_07863#p2:29:406-417, lesson:2026-05-09_10_1145_3805621_3807648#p2:22:0-2514, lesson:2026-02-22_arXiv_2410_13610#p13:201:1824-1851, lesson:2026-05-09_arXiv_2604_08224#p28:189:272-1259
- library receipt: query "blocked task redrive relaunch stale MCP server restart" | release library_graph_20261012_sq013_01_2026-10-12.json sha256:0989759c402ca41472806bdf9ab47529ba2eb5a6b25d0e75c1a6e29e650d4275 | rows lesson:2026-02-22_arXiv_2507_21206#p33:372:2544-3088, lesson:2026-03-17_arXiv_2602_12670#p24:501:1870-2234, lesson:2026-04-13_arXiv_2507_15330#p4:61:1392-1788

The library holds no GitOps, SRE or queueing literature; its hits are lexical on "state", "dispatcher" and "restart" in agent papers (DN-043 R-187 gap, still open).

### Internal

- internal receipt: query "dispatcher reconciles uncommitted machine-written state before clean tree gate" | repo seldon@458ebd777b9919b7884f5b4de34cc31900000772 | hits none
- internal receipt: query "dispatcher reconciles uncommitted machine-written state before clean tree gate" | repo squiddy@1b797f01f7d9acf6ae89548594428521645df834 | hits none
- internal receipt: query "dispatcher reconciles uncommitted machine-written state before clean tree gate" | repo ai-readiness-kg@788400fd7046eafb6e7855e7867e389f2c4bf45b | hits none
- internal receipt: query "dispatcher reconciles uncommitted machine-written state before clean tree gate" | repo arnold@16692cf85fb258be2833a7b08b60c670411a4e2f | hits none
- internal receipt: query "dispatcher reconciles uncommitted machine-written state before clean tree gate" | repo icsp_notebook@ccfb76201f842fb968e7abc1a513d5d1aefdb405 | hits none
- internal receipt: query "dispatcher reconciles uncommitted machine-written state before clean tree gate" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits none
- internal receipt: query "dispatcher reconciles uncommitted machine-written state before clean tree gate" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits none
- internal receipt: query "blocked task redrive relaunch stale MCP server restart" | repo seldon@8b61dd8b82e002a7338ababccc301d26cbd779c3 | hits none
- internal receipt: query "blocked task redrive relaunch stale MCP server restart" | repo squiddy@1b797f01f7d9acf6ae89548594428521645df834 | hits none
- internal receipt: query "blocked task redrive relaunch stale MCP server restart" | repo ai-readiness-kg@788400fd7046eafb6e7855e7867e389f2c4bf45b | hits none
- internal receipt: query "blocked task redrive relaunch stale MCP server restart" | repo arnold@16692cf85fb258be2833a7b08b60c670411a4e2f | hits none
- internal receipt: query "blocked task redrive relaunch stale MCP server restart" | repo icsp_notebook@ccfb76201f842fb968e7abc1a513d5d1aefdb405 | hits none
- internal receipt: query "blocked task redrive relaunch stale MCP server restart" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits none
- internal receipt: query "blocked task redrive relaunch stale MCP server restart" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits none

The lexical search finds nothing because the prior art is by name, not by phrase. Read, not searched: AD-036 ADDENDUM 04 R11 ("An automatic writer commits what it writes"); DESK-001 ("A write that leaves the tree dirty is a defect of the tool, not a chore for the operator"); DESK-002 and DESK-002R; `seldon/commands/dispatch.py:992` ("Blocked, never retried. The next OODA reads the log and decides"); `seldon/core/loaded_state.py` (the stale guard, SEL-006 Part B); Issue 02d52bc4; AD-034 §6; squiddy DN-046, which closed a defect class in one task instead of patching its 20 sites, the pattern this note follows.

The per-writer rule (R11, DESK-001) was right about the duty and wrong about the agent: the duty is that nothing the machine writes is left dirty; the agent that can always discharge it is the one process that holds the lease and already commits before it reads the tree.

## 3. Rulings

- **AD-038-R1. The dispatcher reconciles before it judges.** Before c7 is evaluated, the lease holder commits every dirty path that is machine-written governed state: the event store, the decision register and REGISTER.md, the prior-art query log and verdict ledger, the cadence, registered task files and their addenda. The commit is path-scoped and runs the hooks (R11 kept). The actor allowlist is removed; what qualifies a file is its path class and that its change is append-only or a registration output, never who wrote it. c7 then refuses only on dirt the reconciler could not or may not commit (a source file, a non-append-only ledger change, a hook refusal), and the refusal names that path. **Basis:** OpenGitOps principle 4; measured (797 refusals, all machine dirt).
- **AD-038-R2. A halted task is redriven, not re-issued.** `blocked` gains the transition `blocked -> accepted`, taken by `seldon dispatch redrive <task>` (CLI and MCP), which clears `claimed_by`, records `dispatch_redrive` with the stop it answers, and leaves the task's file, id and history intact. The dispatcher redrives automatically when the stop's cause is one of its own recorded defects (a station that ran in the wrong tree, a database outage); any other cause waits for a redrive from a Desktop or CC session. **Basis:** SQS dead-letter redrive; measured (DESK-002's halt cost one task file, one supersede and 44 minutes).
- **AD-038-R3. The MCP server runs HEAD.** Every mutating seldon-mcp tool runs its command in a fresh subprocess (`python -m seldon ...` from the repository's interpreter) and relays the result; read-only tools may stay in process. `loaded_state.stale` then guards only the read-only tools and never asks for a restart. **Basis:** `importlib.reload` caveats; measured (this session lost every tool at 01:37Z when DESK-002R merged, the third restart in three days).
- **AD-038-R4. A station inspects the tree the session works in.** `part_complete` carries the session's checkout path and branch; the milestone and first-article stations run their checks there. A check that names a file absent from that tree is `unrunnable` (a huddle), never `check_failed` (a stop). **Basis:** AD-037-R6 as written assumed in-place work; measured (02d52bc4).
- **AD-038-R5. Registration runs the task's `check:` premises.** A false premise refuses registration with the command's output, so the author sees it in the same turn. Dispatch keeps its review (the environment may change between). **Basis:** measured (SQ-016, 19 hours to a one-line path error).
- **AD-038-R6. No new control enters the dispatcher without its own negative control and a toil measure.** Every station or gate added from here ships with a test that a correct session passes it, and `seldon qc chart` reports, per week, passes refused on machine dirt and operator interventions (pastes, restarts, re-issues). The target is zero of each; the chart is the evidence. **Basis:** SRE toil budget; Wheeler's charts already adopted in AD-037-R8.

## 4. What this does not change

The gates themselves (prior art, decision register, hooks, premises, stations) stay. This note moves the duty of keeping the tree clean from each writer to the reconciler, and the duty of recovering from a false stop from the operator to the queue. Nothing here lowers a standard; it removes the operator from loops a machine can close.
