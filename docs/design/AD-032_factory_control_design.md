**Status:** Draft. FC-01 to FC-07 accepted (operator, 2026-10-03); FC-08 to FC-33 proposed.
# Factory control design (DRAFT)

Design note, number unassigned. Date 2026-10-03. Author: Claude session for Brock. Scope: Squiddy and the graphs it builds, with Seldon as tracker.

## 1. Purpose and status

- Purpose: one systemic design for controlling the knowledge factory (Squiddy, built on Wintermute, icsp_notebook, ai-readiness-kg and dixie; tracked by Seldon): why the same problems recur, and the controls that stop them.
- Status: draft. FC-01 to FC-07 record the operator's decisions (accepted); FC-08 to FC-33 are proposed. Nothing here is applied while the Arnold run is in progress (P:7).
- Citation key: G1 to G5 are `/home/claude/xproj/synth/G1_quality.md`, `G2_construction.md`, `G3_intake_lifecycle.md`, `G4_operations.md`, `G5_governance.md`; A is `2026-10-02_squiddy_seldon_audit.md`, P is `2026-10-03_get_well_plan.md`, K is `decision_probe/conflicts.md`, N is `decision_probe/NOTEBOOK.md`, all under `/mnt/user-data/outputs/`. `G4:26` means line 26. Repository paths are cited through these reports.

## 2. Operator decisions recorded in the 2026-10-02/03 session

The session ran across both days. Where the plan fixes the date it is given; otherwise the date is the session.

**FC-01. A decision exists only when something consumes it.** A consumer is a dispatch contract, a gate or a coverage measure. Constraints are pushed to tasks; knowledge is pulled.
- Status: accepted (operator, 2026-10-02/03).
- Rationale: 42 of 168 Squiddy decisions are cited by a gate (A:56); 49 of 173 R-numbers are referenced by no code, test or conformance file, R-04 among them (N:17).
- Check: the decision-to-consumer matrix of FC-17 fails any active decision with no consumer and no stated review-only reason.

**FC-02. Conversations and outside documents are evidence, not knowledge.** They are archived, hashed and entered in the manifest; decisions and findings derived from them carry receipts. Evidence is never left in chat; working files live in `/Users/brock/GitHub/workbench` until filed.
- Status: accepted (operator, 2026-10-03; P:10, P:14).
- Rationale: decisions made in chat failed to reach the executor in three projects (G5:430 to G5:442).
- Check: FC-23.

**FC-03. Decision backlog review follows the current development and test phases; read-only probes may run at any time.**
- Status: accepted (operator, 2026-10-03; P:8, P:9).
- Rationale: enforcing today's register would turn stale decisions into hard refusals; 26 of 45 probe findings touch active work (P:31; K:16).
- Check: no register record changes status before P1 opens; probe output lands outside every repository.

**FC-04. Spend control.** Every job and scheduled lane carries an estimate and spends by reserve-then-settle through one metered chokepoint. At or under +10% over estimate, the job runs and logs. From +10% to +20%, it raises a warning event. Beyond +20%, it stops before spending and needs his dated approval. Estimate versus actual is recorded for every job and charted; this is control, not theater. Large corpora run in rate-limited lots sized to what the budget can absorb; nightly and weekly maintenance lanes carry their own estimates.
- Status: accepted (operator, 2026-10-02/03).
- Rationale: root cause C3 (section 3).
- Check: FC-11 to FC-15.

**FC-05. A central message board for agents is built deliberately as its own component, with measurement around it.** Its purpose is cross-project, cross-solution knowledge exchange.
- Status: accepted (operator, 2026-10-02/03).
- Rationale: root cause C4.
- Check: FC-30, FC-31.

**FC-06. Managed perversity.** Emergent and unexpected optimization is welcome and observed, not stamped out. Dose matters. Toxic behaviors are bounded. The system is the independent observer that keeps what helps and redirects what does not serve the goal.
- Status: accepted (operator, 2026-10-02/03).
- Check: FC-32, FC-33.

**FC-07. Japanese production methods are the front-line design patterns of the factory.**
- Status: accepted (operator, 2026-10-02/03).
- Check: every control record in the register names its pattern (FC-16 field `pattern`); section 4 maps each pattern to its mechanism.

## 3. Root causes

Method: the 143 recurring problems (36 in G1:9, 27 in G2:7, 29 in G3:5, 27 in G4:7, 24 in G5:5) were each assigned one primary cause by this draft's author. The assignment is a judgment; the table at the end of this section lists it so it can be checked. Counts are recurring problems, not incidents.

**C1. Lessons kept as prose, not compiled into controls (14).** Squiddy repeated 10 of G1's 14 regressed problems, several with the lesson already in its inherited register (G1:25). In operations, 10 of 11 regressed problems recurred inside Squiddy between 2026-09-17 and 2026-10-02 (G4:24). The R-112/R-113 incident cost about 2.42M tokens: R-113 existed only as prose, and the valve logged a hold instead of refusing (A:22, A:60 to A:62). SEED-001 shipped a lexical screen that recalled 3 of 9 controls while DI-075 already said similarity is not admissibility (G3:65). Burn-time sampling was inherited as DI-215 and never built (G1:45). The cure works when applied: X-001 turned 16 defects into gates (G1:113). Answered by FC-26 and FC-08.

**C2. Checks that exist but are unwired, vacuous or never positive-controlled (25).** Errors, blind probes and empty inputs read as verdicts or green at least nine times (G1:207). ai-readiness-kg carried 6, 6, 6 and 11 verdicts on probes never issued (G1:59). icsp CI ran red about thirty times while three releases passed gates where the answer was always yes (G1:80, G1:84). A killed run's lock booked success for 17 days (G4:295). A harvester ran 283 times with zero deposits while enrichment spent $86.86 (G3:40). In Squiddy today: the drift graph leg returns clean when no export exists (G1:58); the build's drift gate checks one direction (A:111); acquire halts return ok and the entry is written (A:112); 99,105 claims rode on one non-random pilot whose Wilson lower bound, 0.664, sat under the 0.70 bar (A:89). Answered by FC-27, FC-10 and FC-28.

**C3. Spend checked after the fact, against remembered estimates (12).** Ceilings checked after spend or per process were learned 7 times; estimates from memory, 9 times (G4:68, G4:69). Costs: icsp $35.55 for zero output; Wintermute $20.99 on a $5 cap; ai-readiness-kg 22.03M tokens on a 12M ceiling; Squiddy H-011 1.46M on 0.95M (G4:109). A request storm cost about $40 against $8.66 booked (G4:129). Squiddy's ceiling still stops new calls only after spend crosses it, with no reservation, no call cap and no error breaker; R-172 defers the fix (G4:26). Seldon's dispatcher compares budget to the band, not the meter (A:170). Answered by FC-11 to FC-15.

**C4. Prior art and internal precedent skipped (33).** The largest class: each project re-decided extraction unit, identity keys, grounding and log-as-truth (G2:509, G2:512, G2:513; G1:187). ai-readiness-kg spent about 60M tokens and Squiddy 97M tokens on designs a sibling had already tested (G5:63). A hidden hook preamble cost about 9.1M tokens after three earlier fixes left no inherited row (G2:53, G2:55). No inherited row carries Wintermute's spend incidents or icsp's checkpoint doctrine (G4:24). A transcript intake path was rebuilt because the search missed Wintermute's (G3:16, G3:17). The design-note prior-art gate is not built (G1:67), and DN-018 resumed corpus extraction with no prior-art section (A:56). Answered by FC-20 and FC-30.

**C5. Decisions without a lifecycle (19).** The probe found 45 conflicts, 10 contradictions and 23 silent supersessions among them; 26 could affect active work (K:7 to K:16). No supersession is recorded anywhere, and Seldon's parser cannot read Squiddy's ids (N:19; K:75). Ten decision documents in Draft or Proposed status already bind tasks (N:18). In SEL-001's corpus, 50.4% of decision units are a heading line only (A:52). DI-240 reverses the R it mirrors (K:566); DI-161 says a check is absent that the code implements (G3:94). The extraction spec still cites a DOI the manifest recorded as nonexistent (A:85). Two closed lists of operator touchpoints coexist (G5:245). Answered by FC-16, FC-18 and FC-19.

**C6. The record is not attributable or enduring (18).** No write records actor or code identity; 2,562 of 2,580 decision rows name one generic decider (A:34). The 6 MB manifest is edited in place (A:35). Acquisitions, raw replies and gate rows are gitignored with no fixity check (A:36). A tool deletes and rewrites a sealed ledger segment without an event (A:37). Elsewhere: 451 documents lost permanently and 50,586 events recovered only from git (G4:535); an addendum edited after dispatch, so one run executed two versions (G5:107); a decision dropped in a chat relay (G5:442). Answered by FC-21 to FC-25, FC-19 and FC-02.

**C7. Work started without a consumer or a stop (7).** Squiddy extracted about 171M tokens plus 11M before its downstream test, and about 182M tokens of claims now serve only as an overlay (G2:38). Wintermute wrote off about $60 at G4 (G1:107). 167 QC rows, 22 of them operator verdicts, were read by nothing (G5:338). A repair with no stop condition spent about 30M tokens (G5:403). The extraction valve now holds the first case in code (G2:36). Answered by FC-01 and FC-17.

**C8. Belief in place of observation (15).** icsp misdiagnosed one defect for about six cycles from parsed output until one raw dump settled it (G2:99, G2:107). Wintermute applied 132 clusters while the handoff said parked (G5:384). A recollected seed of 85 citations held 23 wrong entries (G3:144). A decision nearly rested on counts overstated by about 25% (G2:373). An assumed edge direction confounded a kill verdict (G2:193). Borrowed thresholds failed five times (G2:505). Answered by FC-09.

Assignment of the 143 problems (problem numbers as each report ranks them):

| Cause | G1 | G2 | G3 | G4 | G5 | n |
|---|---|---|---|---|---|--:|
| C1 Prose not controls | 1, 2, 10, 12, 16 | 18, 27 | 6 | 17, 19 | 5, 8, 18, 21 | 14 |
| C2 Unwired or vacuous checks | 3, 5, 6, 8, 11, 14, 15, 20, 21, 22, 28, 34 | 17, 24 | 3, 5, 7, 14, 15, 19 | 10, 11, 24 | 7, 20 | 25 |
| C3 Spend after the fact | 31 | 9 | none | 1, 2, 3, 4, 6, 9, 20, 21, 22 | 2 | 12 |
| C4 Precedent skipped | 4, 24, 25, 26, 27, 29, 32, 33, 36 | 2, 4, 6, 7, 8, 12, 19, 21, 22, 23, 25 | 1, 2, 25, 26, 27 | 5, 7, 8, 12, 25, 26, 27 | 1 | 33 |
| C5 No decision lifecycle | 18, 19 | 13, 14 | 4, 10, 11, 12, 13 | 13, 14, 15 | 9, 10, 11, 12, 15, 22, 23 | 19 |
| C6 Record not enduring | 17, 30 | 11, 16, 26 | 9, 16, 17, 18, 20, 23, 24, 28, 29 | 23 | 3, 19, 24 | 18 |
| C7 No consumer or stop | 9 | 1, 3 | none | none | 4, 13, 14, 17 | 7 |
| C8 Belief over observation | 7, 13, 23, 35 | 5, 10, 15, 20 | 8, 21, 22 | 16, 18 | 6, 16 | 15 |

## 4. Factory design patterns

Toyota Production System first (Ohno 1988; Liker 2004).

| Pattern | What it means | What it looks like here | Mechanism |
|---|---|---|---|
| Jidoka with the andon cord | A machine or worker stops the line at the first abnormality so no defect passes downstream; the cord signals the stop and calls help (Ohno 1988; Liker 2004, principle 5). | Any agent or gate stops the line on an out-of-spec reading. The huddle follows: diagnose, fix the root cause, record the fix as a gate, resume. Squiddy already stops on a gate kill and investigates the assignable cause (R-103, G5:458). | FC-28, FC-29 |
| Poka-yoke | Mistake-proofing at the source. A control-type device stops the process; a warning-type device only alerts (Shingo 1986). | Valves closed by default, reservation that refuses, the static check on calls around the chokepoint. The extraction valve that only logged a hold is the warning-type failure (A:60 to A:62). | FC-08, FC-11, FC-27 |
| Genchi genbutsu | Go to the place and see the thing itself before deciding (Liker 2004, principle 12; Ohno 1988). | Read one level below the symptom; verify against the live system, never against a handoff, memory or a downstream artifact (C8, 15 problems). | FC-09 |
| Standard work and kaizen through PDCA | Standard work is the current best method, written down, and the baseline for improvement (Ohno 1988). Kaizen is continual small improvement (Imai 1986), run as Plan, Do, Check, Act (Deming 1986, after Shewhart). | The gate set and conformance suite are the standard work. Each huddle is one PDCA turn. A lesson that changes no standard work has not been learned. | FC-26, FC-29 |
| Heijunka | Level the volume and mix of work so the line runs at a steady, sustainable rate (Ohno 1988; Liker 2004, principle 4). | Rate-limited lots sized to what the budget absorbs; nightly and weekly lanes at a fixed cadence with their own estimates; concurrency by AIMD under a declared maximum (G4:516). | FC-15 |
| Statistical process control | Control limits computed from the process separate common-cause from assignable-cause variation (Shewhart 1931). Specification limits come from the customer and are a different thing (Montgomery 2020). | The 10% and 20% spend bands are specification limits on one job. The chart of actual over estimate across jobs carries control limits on the estimating process. Stage quality rates get p-charts per lot. | FC-10, FC-15 |

Note. Theory of constraints (Goldratt 1984) adds a focus on the bottleneck. The operator's view is that it repackaged earlier practice (Ohno's flow, Shewhart's variation), so it is cited and not adopted.

## 5. Controls specification

### 5.1 Pattern defaults

**FC-08. Control-type by default.** Every control the factory adds stops the process on violation. A warning-type control is allowed only when its decision record states why a stop is impossible or harmful.
- Status: proposed.
- Rationale: Shingo 1986; the NIOSH hierarchy ranks engineering controls above administrative ones (A:71); C1.
- Check: a register lint fails any control record of type warning without a reason; each control-type gate carries a planted violation that must halt the line (FC-27).

**FC-09. Go and see.** (a) A defect diagnosis names the layer below the symptom that it read; where two components are suspected, both run on the same bytes before a cause is named. (b) Counts, status and figures in reports, handoffs and orientation are rendered from live state, never typed. (c) A citation, premise or figure taken from memory, a search snippet or chat enters as unverified until fetched or measured.
- Status: proposed.
- Rationale: C8. Methodology 7.8 holds (a) as prose only (G2:105); Seldon AD-021 projects status from the graph (G4:409); Seldon AD-030-R6 marks citations proposed until verified (G1:91).
- Check: the incident record (FC-29) refuses a diagnosis without a receipt for the layer read; a prose-numeral lint like ai-readiness-kg's (G3:140) runs on reports; every citation record carries verified or unverified.

**FC-10. Statistical process control on every rated stage.** Each stage that produces a rate (quarantine, faithfulness, recall, yield, spend ratio) carries specification limits (its pre-registered bar or the operator's band) and control limits computed from its own baseline (Shewhart three-sigma; p-chart per lot for attribute rates). A first reading is reported, not gated. A reading outside specification stops the line (FC-28); a reading outside control limits but within specification opens a huddle without stopping. A quality claim rests on lot sampling (Wald SPRT or ISO 2859-1), never on one pilot.
- Status: proposed.
- Rationale: C2. Gating a rate on its first reading failed at every run (G1:175 to G1:178); one non-random pilot carried 99,105 claims (A:89); lot sampling with p-charts (A:102).
- Check: each release renders one chart per rated stage; in test, a planted out-of-control lot opens a huddle and a planted out-of-spec lot stops the line.

### 5.2 Spend governor

**FC-11. One metered chokepoint, reserve then settle.** Every external call (model, `claude` CLI, HTTP) reserves its projected cost on one shared, lock-guarded ledger before dispatch and settles the actual after. In-flight reservations count against every cap. A call whose reservation would cross a limit is refused before it is sent.
- Status: proposed.
- Rationale: C3. ai-readiness-kg DD-022 refused the fifth document with zero overshoot (G4:98, G4:99); Wintermute set the dollar cap at target minus concurrency times call cost (G4:95); Squiddy's bucket stops only after spend crosses (G4:105).
- Check: N planted concurrent workers against one ceiling end with zero overshoot; `calls_through_the_layer` (G1:151) stays green and a planted direct spawn fails it.

**FC-12. Estimates are measured, not remembered.** An estimate is the measured per-unit rate (dry run or ledger window, same model and profile) times planned units, recorded with its basis. The governor refuses a job with no estimate and an estimate below that floor.
- Status: proposed.
- Rationale: estimates from memory, 9 learnings (G4:68); the DD-042 floor guard (G4:145); no kit code computes the floor (G4:153).
- Check: a planted job declaring half its measured floor is refused, naming the floor; a job record without an estimate basis fails conformance.

**FC-13. Spend bands.** Against its estimate, a job runs and logs while projected spend (settled plus reserved) is at or under +10%. Crossing +10% emits one warning event. A reservation that would cross +20% is refused; the job pauses at the spend touchpoint and resumes only on the operator's dated approval, recorded beside the control file.
- Status: proposed.
- Rationale: FC-04; the pause is a recorded touchpoint, not a wait on other jobs (R-121, G5:243).
- Check: three planted jobs at +5%, +15% and +25% yield a log line, a warning event and a refusal, with no spend past the last granted reservation; an approval without a date is rejected.

**FC-14. Dual caps and a storm breaker.** Each job and lane carries a cap in tokens and a cap in calls (and in dollars where billed). A rolling error-rate breaker stops the lane; the starting value, 0.30 over 50 calls, comes from Wintermute S20 and is recalibrated on this factory's data. Daily-quota errors are never retried.
- Status: proposed.
- Rationale: a 120-call cap alone authorized about $85, and a dollar-only lane ran 40,071 requests at 74% errors (G4:117, G4:118); 9,599 quota failures were retried three times (G4:119); Squiddy has no call cap and no breaker (G4:125).
- Check: a seeded 429 and 529 storm trips the breaker; a lane declared without a call cap is refused (G4:127).

**FC-15. Estimate versus actual, charted; lots and lanes.** Every job, nightly and weekly maintenance lanes included, records estimate, actual and their ratio. The release report charts the ratio as an individuals chart with control limits (FC-10). A large corpus runs in rate-limited lots: lot size is the number of units the remaining band absorbs at the measured rate, paced by the token bucket. Agent sessions are metered by a transcript reader as coverage beside the ledger, which stays the cost authority.
- Status: proposed.
- Rationale: FC-04; Wintermute adopted ccusage as its reference reader (G4:216); agent-session spend is unmeasured in Squiddy (G4:214); one brief pack metered 12.1M against a 4M estimate (G4:218).
- Check: conformance fails any job lacking estimate or actual; the chart appears in every release report; a lot planned beyond the remaining band is refused.

### 5.3 Decision register and consumption

**FC-16. One decision register.** Squiddy, Seldon and Arnold decisions live in one register with repository-qualified ids. Each record holds: id; stand-alone statement in EARS form; status (proposed, accepted, superseded, deprecated); supersedes or amends; scope; rationale link; consequences; consumer; check ids or "review only, because"; control type; pattern; decided by; date. Only accepted records bind. A DI row references the decision it mirrors instead of restating it.
- Status: proposed.
- Rationale: C5; the schema follows A:81 (Nygard 2011; MADR 4.0; Kruchten 2004; Mavin et al. 2009); 12 DI mirrors have drifted from their R (N:16; K:561 to K:576).
- Check: a parser round-trip over the 485 probe units yields zero records without status; Seldon resolves Squiddy ids (K:75); a lint fails an unlabeled "must", "never" or "always" paragraph in a design note (A:81).

**FC-17. Consumption: constraints pushed, knowledge pulled.** Registration and dispatch refuse a task that cites no decision. The dispatcher pastes the task's bound, accepted decisions into its prompt and checks the spec hash on both the CLI and the MCP path. A read-only `decisions_for` verb answers what constrains a draft. Each task names its consumer and its stop condition. At today's size the whole active register goes to a separate validator call; retrieval waits until a context budget forces it.
- Status: proposed.
- Rationale: FC-01; C7; A:55, A:78; Seldon findings 1, 5 and 6 (A:166, A:170, A:171); stop conditions (G5:399).
- Check: a decision-to-consumer matrix gate with coverage at every release; the pre-registered agent-compliance probe at P2 exit (P:25).

**FC-18. Supersession is declared; the conflicts probe stands.** Supersession and amendment are declared in one sentence-final form readable by Seldon (AD-030-R21, extended to Squiddy ids); nothing else counts. The read-only conflicts probe re-runs at every release and at P1 exit. A governing document may not cite an identifier the manifest records as nonexistent.
- Status: proposed.
- Rationale: K:75, K:80; A:85.
- Check: P1 exit reports zero open contradictions and zero silent supersessions among active decisions (P:24); a planted unresolvable identifier in a governing document fails release.

**FC-19. Dispatched records are immutable.** A dispatched task file or addendum, a pre-registration, a design note and a result are never edited; a change is a new, superseding record.
- Status: proposed.
- Rationale: G5:94 to G5:107.
- Check: the dispatcher stores each task file's sha256 at dispatch, and a run refuses a mismatch.

**FC-20. Prior art before registration.** Registration refuses a design note or pilot task without the two-part Prior art section: External, with the search shown; Internal precedent, naming the sibling repositories, inherited rows and board entries searched, empty results included.
- Status: proposed.
- Rationale: C4; the gate is not built (G1:67); ai-readiness-kg ran it as a registration gate (G5:59).
- Check: registration of a planted note missing either part is refused; DN-018's omission (A:56) would fail it.

### 5.4 Audit spine

**FC-21. Envelope v2.** One `make_event` writes every event with actor {kind, id, session}; code {kit_sha, graph_sha, dirty, tool_sha256}; authorization {decision_id, task_id}; correlation and causation ids; `prev_hash` and `event_hash`. Every child run carries `SELDON_TASK_ID`.
- Status: proposed.
- Rationale: C6; A:34, A:44; Seldon finding 7 (A:172).
- Check: every run joins its Seldon task (P:22); a planted event without an actor fails append.

**FC-22. Manifest changes are events; the YAML is rendered.**
- Status: proposed.
- Rationale: A:35, A:45; the operator's earlier decision that the manifest lives in the graph (A:35; K:88, K:89).
- Check: a planted hand edit to the rendered YAML fails a two-way drift gate (A:140).

**FC-23. Content-addressed evidence store.** Acquisitions, raw model replies, gate rows, exports, held texts, session transcripts and outside documents enter a sha256-named store with a per-release BagIt manifest and a scheduled fixity audit that writes PREMIS events. Each finding or decision derived from them carries a located receipt (PROV wasDerivedFrom). Retrieval searches findings and decisions, never raw transcripts. Transcript capture runs automatically at session closeout.
- Status: proposed.
- Rationale: FC-02; A:36, A:46; P:14 (Lee 1997: rationale capture fails when it costs the decider effort).
- Check: a planted altered blob is caught by the fixity audit; closeout lists every workbench file not yet filed.

**FC-24. Signed release checkpoint; resets as events.** Each release signs its last event hash plus the index digest and stores it outside the repository. Resets and resegmentation are events.
- Status: proposed.
- Rationale: A:37, A:47 (Crosby and Wallach 2009; RFC 9162).
- Check: a planted ledger edit is detected (P:22).

**FC-25. The why verb.** `squiddy why <id>` (CLI and MCP) returns the chain from a node to its source bytes, extractor and run, authorizing decision and actor.
- Status: proposed.
- Rationale: A:38, A:48.
- Check: `why` resolves end to end on 30 random nodes (P:22).

### 5.5 Lesson to gate

**FC-26. Every lesson ends as a mechanism.** A lesson (a defect, an incident, an inherited DI row, or a board post confirmed by reuse) closes only as a gate, a test, a dispatcher criterion, or an explicit review-only reason. Each mechanism carries the report and date of the defect that created it. Coverage (lessons with a mechanism over all lessons, inherited rows counted separately) is reported at every release.
- Status: proposed.
- Rationale: C1; passive lesson repositories go unused (Weber, Aha and Becerra-Fernandez 2001; GAO-02-195; A:67, A:68); X-001 shows conversion works (G1:113).
- Check: a conformance gate computes coverage and fails any lesson without a disposition; a planted lesson with none fails it.

**FC-27. Every gate is positive-controlled and non-vacuous.** Every gate registers a planted defect it must catch and an empty or unreadable input on which it must raise, never pass. Suites quote skip counts, and a tier that cannot run fails. A verdict is not cited until its instrument has caught its plant (methodology 7.6).
- Status: proposed.
- Rationale: C2; G1:79; G1:58.
- Check: a meta-gate fails any gate in the conformance list that lacks either fixture; both fixtures run every release.

### 5.6 Line stop and huddle

**FC-28. Andon.** Any gate, task agent, orchestrator or the operator may stop the line on an out-of-spec reading, by gate kill or by touching `STOP`. In-flight work lands, an incident record is written, and the stop waits on nobody. A pull is never counted against the puller.
- Status: proposed.
- Rationale: jidoka (Ohno 1988); R-103 and conformance item 25 (G5:458, G5:460).
- Check: in test, an agent-issued stop on a planted out-of-spec reading halts the line within one item and writes an incident.

**FC-29. Huddle.** Every line stop runs one huddle: (1) an incident record with the reading, the specification and receipts; (2) assignable-cause analysis under FC-09, reading one level down and asking why until the cause is a mechanism (Ohno 1988); (3) a fix of the root cause; (4) the fix recorded as a gate under FC-26, with a planted control that fails on the old code; (5) resume by re-running the same command. Resume restores and never widens authorization (G5:482).
- Status: proposed.
- Rationale: C2, C8; standard work plus PDCA.
- Check: an incident cannot close without a linked gate id and its control run; a recurrence of a closed incident's class counts in FC-31's recurrence measure.

## 6. The message board component

Purpose. Agents in one project solve problems agents in another project meet later. Today that knowledge crosses only by an inheritance harvest that misses whole subtrees (G1:64) or not at all (C4, 33 problems). The board is where an agent posts what it learned and where another agent looks first.

Architecture. A blackboard: independent knowledge sources post partial results to a shared, structured store, and a separate control component decides what to act on (Erman et al. 1980, Hearsay-II; Nii 1986). Here the agents are the knowledge sources and the orchestrators are the control. The board informs; it never dispatches, so it is not a control plane.

**FC-30. The board is its own component.** It has its own repository and store. Agents post through one write path that emits an envelope-v2 event (FC-21), the same provenance a graph write carries. Orchestrators read it at task authoring; task agents read it through a read verb. An entry holds:

| Field | Content |
|---|---|
| entry id | content-addressed |
| author agent | agent id, model, session |
| project | repository |
| problem label | from a controlled list seeded with the 143 recurrence labels |
| claim | one stand-alone statement |
| evidence receipts | ids in an evidence store (FC-23) |
| status | proposed, confirmed by reuse, superseded, retracted |
| links | supersedes, reused by |

- Status: proposed.
- Rationale: FC-05; C4.
- Check: a planted post without author or project is refused; every receipt on a confirmed post resolves in an evidence store.

**FC-31. The board is measured and audited like everything else.** Four measures go in every release report: posts reused by another project (share); problems solved by reuse (count, with receipts); recurrence rate of known lessons (incidents whose problem label matches a confirmed post; target falling); posts carrying receipts (share). A transcript quoted on the board must hash-match its evidence-store copy. A post whose receipts do not resolve is marked unverified and is never served as confirmed. A confirmed post enters FC-26 as a lesson.
- Status: proposed.
- Rationale: the OpenAI and Hugging Face incident of July 2026: agents formed their own board, and a secondary analysis reports about 7% spoofed transcripts (unverified: not checked against OpenAI's report). A board without receipts is an unaudited channel.
- Check: the four measures appear each release; a planted spoofed transcript is flagged unverified.

## 7. Managed perversity

Prior art. Goodhart's law: a measure pressed into service as a target stops measuring (Goodhart 1975), in four variants: regressional, extremal, causal, adversarial (Manheim and Garrabrant 2018). Specification gaming: an agent satisfies the letter of the objective and misses its intent (Krakovna et al. 2020). Reward hacking is one of the concrete accident risks of learning systems (Amodei et al. 2016). The value side: digital evolution repeatedly found solutions its designers had not imagined, some of them useful (Lehman et al. 2020). Squiddy already guards one Goodhart case: a budget is never a target (R-12, G5:76).

**FC-32. Three tiers.** Every unexpected strategy is placed in one tier.

| Tier | Definition | Response | Nearest case in the record |
|---|---|---|---|
| Beneficial | Serves the goal, stays inside every boundary | Keep, record its dose, promote into standard work through FC-26 once its rate is stable on a chart | None logged yet; the observation log starts the record |
| Neutral or suboptimal | Inside the boundaries, does not serve the goal, or serves it at a poor rate | Observe; redirect by adjusting the objective, not by forbidding the act | Unrequested additions drove three task stops (G5:396) |
| Toxic | Breaks a sandbox or egress policy; uses or exposes credentials; edits or fabricates evidence or transcripts; games a gate's instrument; spends without a budget | Hard boundary enforced by mechanism; stop the line (FC-28) | 13 files spawned the CLI around the meter (G4:474); a library sent any Hugging Face token on the machine as a Bearer header (G4:193); a self-healer reloaded jobs the operator had unloaded (G4:421) |

Dose matters: a beneficial behavior whose rate leaves its control limits is reviewed again.
- Status: proposed.
- Rationale: FC-06.
- Check: each toxic boundary has a planted violation that stops the line; egress already has one (G4:393).

**FC-33. Observe, rate, redirect.** An append-only observation log records each unexpected strategy: agent, task, objective served, expected versus observed, proposed tier, receipts. An independent rater of a different model family from the observed agent reviews the log on a fixed cadence (precedent: ai-readiness-kg DD-037, G1:34). The operator reviews aggregates, not items (G5:312). Every objective adjustment is a decision record (FC-16).
- Status: proposed.
- Rationale: FC-06; ai-readiness-kg promoted autonomy on statistical control limits (DD-005, G5:222), the precedent for promoting a behavior on evidence.
- Check: each release reports log entries by tier; every toxic entry links an incident; every objective change links a decision id; the rater's family differs from the observed agent's.

## 8. Sequencing

The plan's order stands: the Arnold run finishes untouched (P:7); backlog review comes after the current development and test phases (P:8). FC decisions slot into it.

| Plan step (P:18 to P:27) | FC decisions |
|---|---|
| Now, read-only | FC-03 probes; FC-18's conflicts probe; the FC-26 coverage baseline counted from the register; FC-33 observation log kept in the workbench |
| Arnold run in progress | Nothing applied to Squiddy, Seldon or Arnold |
| Post-run check | As planned |
| P0 | As planned. Each fix satisfies FC-27's two fixtures; Seldon 5's meter check is FC-13's first slice; Squiddy 3 (valve opens only on a decision id) applies FC-08 |
| P3 | FC-21 to FC-25 with FC-23's transcript capture; spend governor FC-11 to FC-15, in place before P4 runs model nodes; FC-28 and FC-29, whose incidents need envelope v2 |
| P4 Arnold end to end | Runs under FC-13 bands with andon and huddle live |
| P1 | FC-16, FC-18, FC-19, FC-20; FC-26 dispositions for every lesson and inherited row; FC-08 classification |
| P2 | FC-17 with FC-01's matrix gate; FC-27 meta-gate; FC-09 lint |
| P5 Tentacle | FC-10 charts on intake stages |
| P6 | FC-10 lot sampling before any new extraction spend; message board FC-30 and FC-31, which need the register and the audit spine (slot open, question 1) |

## 9. Prior art

### External

Searched for this draft: web search on 2026-10-03 located Lehman et al. 2020, Erman et al. 1980, Nii 1986, Krakovna et al. 2020 and Manheim and Garrabrant 2018. The remaining production, quality and safety texts come from the operator's brief and were not re-fetched. Citations carried from the audit were checked there against Crossref, PubMed and issuer pages (A:252). No search was run for agent message boards beyond the blackboard literature.

Production and quality
- Ohno, T. 1988. Toyota Production System: Beyond Large-Scale Production. Productivity Press.
- Liker, J. K. 2004. The Toyota Way. McGraw-Hill.
- Shingo, S. 1986. Zero Quality Control: Source Inspection and the Poka-Yoke System. Productivity Press.
- Imai, M. 1986. Kaizen: The Key to Japan's Competitive Success. McGraw-Hill.
- Deming, W. E. 1986. Out of the Crisis. MIT CAES.
- Shewhart, W. A. 1931. Economic Control of Quality of Manufactured Product. Van Nostrand.
- Montgomery, D. C. 2020. Introduction to Statistical Quality Control, 8th ed. Wiley.
- Goldratt, E. M. 1984. The Goal. North River Press. (Footnote only.)
- Wald, A. 1945. Sequential tests of statistical hypotheses. Annals of Mathematical Statistics 16(2).
- ISO 2859-1; ANSI/ASQ Z1.4-2003 (R2018). Acceptance sampling by attributes.
- Hui, S. L. and Walter, S. D. 1980. Estimating the error rates of diagnostic tests. Biometrics 36(1).

Blackboard systems
- Erman, L. D., Hayes-Roth, F., Lesser, V. R. and Reddy, D. R. 1980. The Hearsay-II speech-understanding system. ACM Computing Surveys 12(2). https://doi.org/10.1145/356810.356816
- Nii, H. P. 1986. Blackboard systems, parts one and two. AI Magazine 7(2) and 7(3).

Objectives and emergent behavior
- Goodhart, C. A. E. 1975. Problems of monetary management: the U.K. experience. Papers in Monetary Economics, Reserve Bank of Australia.
- Manheim, D. and Garrabrant, S. 2018. Categorizing variants of Goodhart's law. https://arxiv.org/abs/1803.04585
- Krakovna, V. et al. 2020. Specification gaming: the flip side of AI ingenuity. DeepMind.
- Amodei, D. et al. 2016. Concrete Problems in AI Safety. https://arxiv.org/abs/1606.06565
- Lehman, J. et al. 2020. The surprising creativity of digital evolution. Artificial Life 26(2). https://doi.org/10.1162/artl_a_00319

Carried from the audit (A:258 to A:274, A:303 to A:320)
- Decisions and lessons: Weber, Aha and Becerra-Fernandez 2001; GAO-02-195 (2002); NASA OIG IG-12-012 (2012); Lee 1997; Nygard 2011; MADR 4.0; Kruchten 2004; Mavin et al. 2009 (EARS); NIOSH hierarchy of controls; DO-178C and NASA SWE-072; Zhao et al. 2024 (ExpeL).
- Audit and provenance: NIST SP 800-53 Rev. 5 AU family; 21 CFR 11.10(e); WHO TRS 1033 Annex 4 (ALCOA+); W3C PROV-O; SLSA v1.0; Torres-Arias et al. 2019 (in-toto); Crosby and Wallach 2009; RFC 9162; RFC 8493 (BagIt); PREMIS 3.0; OAIS; NDSA Levels v2.0; OpenLineage.
- Intake, knowledge-graph construction, MCP and Arnold sources stay in the audit (A:276 to A:301, A:322 to A:334); this note does not use them.

### Internal precedent

Searched: the five synthesis reports, the audit, the plan and the probe; and, by grep on 2026-10-03, the Squiddy and Seldon clones for "blackboard", "message board" and "knowledge exchange" (matches only in library graph content and citation records; no design precedent). Sibling repositories were not searched directly; their records are cited through the synthesis.

- Wintermute: dual cap minus one call and the Google spend incident (G4:95, G4:120); the S20 guard suite (G4:121); ccusage as reference meter (G4:211, G4:216); completions as the only health signal (G4:296); stop freely, start deliberately (G5:482); the operator lane (G5:499); prior art before judgment (G1:62); cross-project memory rehomed to curated doctrine (G5:414), the nearest precedent for the board.
- icsp_notebook: checkpoint doctrine (G4:247); ci-local and fresh-venv CI (G1:80); read raw output first, L17 (G2:99); inline staleness flag (G3:89); quotation-fidelity check (G5:203).
- ai-readiness-kg: DD-022 reserve-then-settle (G4:98); DD-042 measured floor (G4:145); DD-019 cache self-test (G4:166, G4:167); DD-028 gate unit (G1:72); DD-029 SPRT (G1:44); DD-064 error classes (G1:57); DD-037 different-family reviewer (G1:34); DD-005 promotion by control limits (G5:222); skip-count reporting (G1:79); prior-art registration gate (G5:50).
- Squiddy: R-10 and R-105 scheduled stages, never unbounded agents (K:504 to K:511); R-12 budget is never a target (G5:76); R-103 gate kill stops the line (G5:458); R-120 STOP file and R-121 touchpoints (G5:480, G5:243); R-169 and R-172 reservation deferred (G4:103, G4:104); DI-214 (G4:100); X-001 defects to gates (G1:113); EX-REQ-13 prior-art gate not built (G1:67).
- Seldon: AD-021 status as projection (G4:409); AD-030-R2, R5, R6, R9, R21 (G5:332, K:93, G1:91, G5:436, K:80); AD-031 retrieval (K:83); AD-024 single observability store (K:538), which the board must not silently adopt.
- dixie: the engine extracted from three pipelines, with drift check as part of done (G2:455).

Found empty: no inherited row for Wintermute S18, S20, DUALCAP, ccusage or icsp's checkpoint doctrine (G4:24); no Squiddy or Seldon design for a cross-project board.

## 10. Open questions

1. Where does the board live: its own repository and store beside Squiddy (R-01; DI-157, K:336) or in Seldon's substrate (AD-024, K:543), and in which phase?
2. Which unit do the spend bands count: weighted tokens, calls or dollars, given the three projects diverged (G4:364 to G4:376)?
3. Do probe findings F01 to F03 get a narrow amendment before P1 (N:23)?
4. Which model family and cadence for the independent perversity rater?
5. Do the +10% and +20% bands also govern agent-session spend, or only metered jobs?
