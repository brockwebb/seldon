# AD-038 ADDENDUM 16: a coordination lane beside an exclusive build, a project's own premises, one minted identity per session, and every limit tried by a plant

**Date:** 2026-11-27. **Status:** Accepted. Implemented by SEL-054 Parts A and B
(`cc_tasks/2026-11-27_SEL-054_four_things_the_factory_needs_from_the_dispatcher_are_built.md`), from factory's filings
`cc_tasks/2026-11-27_filing_from_factory_a_coordinator_task_launches_beside_an_exclusive_build_task.md`,
`cc_tasks/2026-11-26_filing_from_factory_a_project_needs_a_premise_the_dispatcher_evaluates_for_every_task_so_a_spent_grant_stops_new_launches.md`,
`cc_tasks/2026-11-27_filing_from_factory_the_dispatcher_mints_one_hive_identity_per_session_at_launch.md` and
`cc_tasks/2026-11-27_filing_from_factory_every_limit_the_dispatcher_sets_is_tried_by_a_planted_control.md`.
**Extends:** SEL-004's planner (`plan_launches`, writer preference) with a reserved class; DN-006 decision 9 (FIFO)
with a class named in configuration; AD-037-R6 (a) (station (a)) with premises the project declares; AD-037-R17 (the
lease's phases) with a holder that writes main between its session's ticks; AD-032 FC-27 applied to the dispatcher's
own limits. Six new rulings, AD-038-R40 to R45.
**Code:** `seldon/core/lane.py`, `seldon/core/hive.py`, `seldon/core/controls.py` (new);
`seldon/commands/dispatch_lane.py` (new); `seldon/core/dispatch.py` (`load_dispatch_config`, `plan_launches`,
`fifo`, `REFUSAL_REASONS`); `seldon/commands/dispatch.py` (`_pass`, `_launch_inplace`, `_session_settings`, `_run`,
`_launch_gates`, `_project_premise_gate`, `_controls_gate`, `_hive_env`, `try_limits`, `seldon dispatch controls`);
`seldon/commands/dispatch_worktree.py` (`pass_parallel`, `_start_claimed`, `_supervise`, `finish_session`, `_merge`);
`seldon/commands/dispatch_stations.py` (`tool-gate --deny-path`).
**Tests:** `tests/test_sel054_launch_path.py`, `tests/test_sel054_identity_and_controls.py`; the serial transcript
fixture re-recorded for one line (R45's record joins the first launch's record commit).

## 1. Evidence

1. **A check-in queued behind the build it watches.** factory, 2026-11-26 about 22:40 EST: OODA-001 (filed for
   critical-thinking-ai CTAI-008's `merge_blocked: ungated`) waited behind FAC-31, an exclusive 1.8M build, for that
   task's length while twelve changes waited behind "an OODA is open"; the block held for ninety minutes until a
   Desktop thread landed it by hand (CTAI-008R). Read at seldon main: `plan_launches` defers every candidate while an
   exclusive task is held, and an exclusive task's holder keeps the pass lease for its whole session, so no pass runs
   at all while a build does.
2. **A spent grant stops only the tasks that carry its premise.** factory FAC-30: `cost_manager.py status --stop-only`
   exits 4 naming the grant when a project's weekly grant is spent. Station (a) runs a task's own `**Premises:**`, and
   adds one of its own (`environment_in_flight`); a project cannot declare another, and the STOP file also stops
   merges, redrives and the stuck alarm.
3. **An identity attested by the client.** factory FAC-31 (DN-005): each session minted its own board identity from a
   minter token every session can read, so a session could mint a second one naming another project.
4. **A limit that matched nothing and said nothing.** FAC-31 Part C, control C5: `Write(/private/tmp/.../check/**)`,
   whose single leading slash is relative to the settings file in Claude Code's rule syntax, let the control's write
   through; with `//` the same write was refused. None of the eight planted sessions before it had tried a limit.

## 2. Prior art

### External

- **Reserved capacity for a named class of work.** Slurm's Quality of Service (a QOS reserves and limits resources
  for a class of jobs, named once by the administrator); Kubernetes PriorityClass, whose `system-cluster-critical`
  class names a class of pods rather than a priority each author sets; GitHub Actions `concurrency` groups (one
  running per group). Named from their documentation, not fetched here. Adopted for R40: the lane is a class named
  once in `seldon.yaml`, with its own slots. DN-006 decision 9's refusal of a per-task priority field stands.
- **Readers-writer locking** (Courtois, Heymans and Parnas, CACM 1971), already cited by `plan_launches` for writer
  preference: a writer needs exclusion only from parties that touch what it writes. Adopted for R40/R41: a lane task
  may run beside an exclusive build because what it may change is declared and the merge refuses the rest.
- **Admission control at the head of a queue** (Kubernetes validating admission and ResourceQuota: a policy evaluated
  for every new pod, refusing new work and never touching running pods). Named, not fetched. Adopted for R42.
- **Workload identity attested by the platform at launch** (SPIFFE/SPIRE: the agent attests a workload and issues its
  SVID, the workload never holds the signing key; Kubernetes projected service-account tokens mounted by the kubelet).
  Named, not fetched. Adopted for R43.
- **Controls assessed by trying them** (NIST SP 800-53 Rev. 5 CA-2 control assessments and CA-8 penetration testing;
  negative testing of an access control: a request it must refuse). Named, not fetched. Adopted for R45, with AD-032
  FC-27 (below) as the internal statement of the same rule.
- **Claude Code's permission-rule path syntax** (code.claude.com/docs, "Identity and Access Management", Read and Edit
  rules: `//path` absolute, `~/path` home, `/path` relative to the settings file, `path` or `./path` relative to the
  working directory). Named, not fetched; FAC-31's C5 and C5b are the observation.
- The library arm returned nothing on point:
  - library receipt: query "reserved capacity for a class of work beside an exclusive job" | graph seldon-biblio | release seldon_biblio_graph_20261111_sel037_2026-11-11.json sha256:076422bb8382009ff8c0105c7ae07dd9b2f2a86b7ff7fd24b4674e219c6b7b4c | rows doc_who_trs1033_annex4_1#b1042:312820-313126, doc_who_trs1033_annex4_1#b2136:564061-564579, doc_who_trs1033_annex4_1#b1883:506761-506820, doc_rfc8493_1#b112:18452-18748, doc_omg_kerml_1#b1014:329617-329787, doc_omg_kerml_1#b3212:586779-587415, doc_omg_kerml_1#b3214:587693-588011, doc_rfc9162_1#b238:41011-41243, doc_rfc9162_1#b56:13567-13617, liang2026skillnet#b196:85617-86184, liang2026skillnet#b158:66611-66980, liang2026skillnet#b173:70982-71216, gotel1994traceability#b82:29371-29495, gotel1994traceability#b34:7910-8302, gotel1994traceability#b45:11379-11542, niosh_hierarchy_of_controls#b45:4197-4209, ilyas2023growing#b12:2304-2656, ilyas2023growing#b66:22771-22958, ilyas2023growing#b74:26641-27410, doc_omg_sysml_v2_1#b3237:743681-743773, doc_omg_sysml_v2_1#b1508:497332-497384, doc_omg_sysml_v2_1#b3646:784186-784504, arxiv_2406_14325#b115:62816-63838, doc_w3c_prov_o_1#b326:36826-36926, aaai_v40i44_41105#b9:2721-2834, doc_omg_reqif_1_2_1#b377:80872-80946, doc_omg_reqif_1_2_1#b1404:120431-120576, doc_omg_reqif_1_2_1#b1367:118291-118470, zhao2024expel#b1:25-138, doc_sw_openfasttrace_ug_reference_xml_tracing_report#b24:4121-4415, doc_sw_openfasttrace_ug_reference_xml_tracing_report#b25:4416-4666, doc_nasa_swe_072_1#b555:95679-96282, doc_nasa_swe_072_1#b290:46380-47117, doc_nasa_swe_072_1#b388:61897-62056, doc_sw_openfasttrace_ug_use_cases_use_cases#b6:807-998, doc_sw_openfasttrace_ug_use_cases_use_cases#b8:1197-1352, clark2014micropublications#b74:21573-21629, clark2014micropublications#b139:41738-42051, amodei2016concrete#b312:112218-112375, doc_sw_openfasttrace_ug_use_cases_delegating_requirement_coverage#b5:1181-1328
  - library receipt: query "workload identity issued at launch" | graph seldon-biblio | release seldon_biblio_graph_20261111_sel037_2026-11-11.json sha256:076422bb8382009ff8c0105c7ae07dd9b2f2a86b7ff7fd24b4674e219c6b7b4c | rows doc_nasa_swe_072_1#b834:160763-161072, doc_nasa_swe_072_1#b995:180227-180318, doc_nasa_swe_072_1#b849:162271-162460, doc_who_trs1033_annex4_1#b2001:522392-522537, doc_who_trs1033_annex4_1#b1227:345302-345405, doc_who_trs1033_annex4_1#b1948:513386-513427, nasa_oig_ig_12_012#b92:31862-32142, nasa_oig_ig_12_012#b186:69299-69583, nasa_oig_ig_12_012#b26:8058-8668, doc_omg_reqif_1_2_1#b1250:114198-114496, doc_omg_reqif_1_2_1#b186:61175-61476, doc_omg_reqif_1_2_1#b18:5825-6349, nasa_swe_072#meta, doc_premis_3_0_1#b34:15965-16103, doc_premis_3_0_1#b139:52679-53079, doc_premis_3_0_1#b103:39511-40229, doc_rfc8493_1#b165:27882-27949, doc_rfc8493_1#b170:28298-28455, doc_rfc8493_1#b166:27951-28147, aaai_v40i44_41105#b10:2836-3154, ilyas2022saga#b22:6782-7168, ilyas2022saga#b124:44917-45357, ilyas2022saga#b93:31061-32001, scukanec2010verification#meta, doc_rfc9162_1#b165:27885-28357, doc_rfc9162_1#b172:28759-28997, doc_rfc9162_1#b188:30843-31086, doc_omg_sysml_v2_1#b599:284331-284975, doc_omg_sysml_v2_1#b1959:625174-625439, doc_omg_sysml_v2_1#b3725:814288-814620, doc_omg_kerml_1#b573:225564-225802, doc_omg_kerml_1#b779:278638-279227, doc_omg_kerml_1#b14:6759-9944, gotel1994traceability#b35:8304-9362, gotel1994traceability#b169:51957-52068, doc_sw_requiem_1#b16:591-753, browning2014doorstop#b9:548-1368, browning2014doorstop#b41:9916-10378, browning2014doorstop#b44:11151-12006, doc_sw_openfasttrace_ug_use_cases_distributing_the_detailing_work#b3:384-895, ilyas2023growing#b69:23386-24570, ilyas2023growing#b72:24931-25580, ilyas2023growing#b12:2304-2656, zhang2026rlm#b26:10226-10671, zhang2026rlm#b32:11644-12295, zhang2026rlm#b51:19014-19665, yu2026multiagentmemory#b47:6849-7342
  - library receipt: query "every control is tested by a request it must refuse" | graph seldon-biblio | release seldon_biblio_graph_20261111_sel037_2026-11-11.json sha256:076422bb8382009ff8c0105c7ae07dd9b2f2a86b7ff7fd24b4674e219c6b7b4c | rows doc_who_trs1033_annex4_1#b1841:498252-498459, doc_who_trs1033_annex4_1#b1290:357906-358022, doc_who_trs1033_annex4_1#b1772:482689-483167, doc_nasa_swe_072_1#b364:57686-58363, doc_nasa_swe_072_1#b249:38769-39127, doc_nasa_swe_072_1#b470:81700-81785, doc_rfc8493_1#b163:27751-27815, doc_rfc8493_1#b164:27817-27880, doc_rfc8493_1#b165:27882-27949, doc_sw_sphinx_needs_2#b71:2038-2820, doc_omg_sysml_v2_1#b2256:646893-646962, doc_omg_sysml_v2_1#b1020:389316-389375, doc_omg_sysml_v2_1#b3944:867108-867519, doc_rfc9162_1#b484:86305-86437, doc_rfc9162_1#b179:29394-29463, doc_rfc9162_1#b184:29961-30000, clark2014micropublications#b526:117181-117505, doc_sw_openfasttrace_ug_reference_input_format_support#b9:1038-1166, doc_omg_kerml_1#b5048:793598-793813, doc_omg_kerml_1#b1055:336670-336970, doc_omg_kerml_1#b618:238318-238662, amodei2016concrete#b252:102862-102989, amodei2016concrete#b184:92285-92397, amodei2016concrete#b83:45037-45487, doc_sw_sphinx_needs_1#b2254:43040-43452, niosh_hierarchy_of_controls#b57:5206-5335, doc_sw_requiem_1#b47:3126-3230, doc_sw_autoresearch_1#b13:3138-3241, doc_sw_autoresearch_1#b31:6743-7048, doc_sw_openfasttrace_ug_reference_xml_tracing_report#b25:4416-4666, doc_sw_madr_1#b41:4856-4935, zhuge2024agentjudge#b342:88916-89155, zhuge2024agentjudge#b340:88683-88904, zhuge2024agentjudge#b319:87302-87432, fuchss2025lissa#b110:33238-34039, fuchss2025lissa#b122:38395-38845, fuchss2025lissa#b157:64557-65500, doc_argondigital_verification_methods_1#b30:7366-7515, aaai_v40i44_41105#b75:26067-26847, aaai_v40i44_41105#b22:7317-7700

### Internal

- internal receipt: query "planted control deny rule" | repo seldon@e9018d6e5a1bd14ebad13bd436057a77c7272abc | hits docs/decisions/REGISTER.md:9
- internal receipt: query "planted control deny rule" | repo squiddy@82c97c47a5787009daee2b7b70e37ff0ac10a634 | hits docs/X-002_delivery_report.md:353, docs/DECISIONS_INHERITED.md:508, docs/decisions/REGISTER.md:9
- internal receipt: query "planted control deny rule" | repo factory@1e840a30e5b8316c6b2b79c58e0b401969de663c | hits docs/plan.md:118
- internal receipt: query "Hive identity mint" | repo factory@1e840a30e5b8316c6b2b79c58e0b401969de663c | hits docs/design/2026-11-26_DN-005_the_hive_is_msgboard_on_this_machine_a_post_is_context_and_answers_reach_a_session_by_code.md:95, docs/decisions/register/00058_factory-f-046_accept.yaml:29, docs/decisions/register/00058_factory-f-046_accept.yaml:1

What the record held: AD-032 FC-27 ("Every gate is positive-controlled and non-vacuous. Every gate registers a planted
defect it must catch", `docs/design/AD-032_factory_control_design.md`) is the rule R45 applies to the dispatcher's own
limits; factory's DN-005 decision 2 and F-046 (the register record the internal arm found) define the identity R43
mints; factory's `docs/plan.md` names the planted controls of FAC-31.

## 3. Rulings

- **AD-038-R40. A project may declare one coordination lane, `dispatch.coordination_lane: {name_pattern, slots, writes, merge_wait_s}`: a task whose graph name matches `name_pattern` goes first among eligible candidates, always runs in its own worktree under its own supervisor, takes one of `slots` reserved slots and no `max_parallel` slot, and is neither held back by an exclusive task, running or waiting, nor holds one back; while an exclusive task runs, its holder looks for a lane task at each inspection tick and launches it under the pass lease it already holds.**
  Every other gate stands for a lane task: candidacy, band, Spend ceiling, station (a), the project's launch gates
  (R42, R45), the stop gate, the merge lock and the re-gate. c6 for a lane task is a free lane slot, held while its
  supervisor's worktree lease is held, whatever the graph says meanwhile. The holder's look marks the lease `pass`
  while it writes main and `session` after (AD-037-R17); a failed look is recorded (`dispatch_lane_error`) and never
  reaches the build it runs beside. A lane supervisor waits for the pass lease at its finish up to `merge_wait_s`
  (default 14,400 s, no measured basis: above FAC-31's ninety minutes), because a build's holder keeps it for the
  build's whole session. AD-037-R9's condition for a second session (stations and the disk preflight live) holds: the
  lane's launch runs c12 and station (a) like any other.
- **AD-038-R41. A lane task's branch may change only the paths its lane's `writes` declares, with its own RESULT, the `merge=union` files and the gate record's ledger exempt; the merge round refuses anything else as `merge_blocked` with reason `lane_wrote_outside`, naming the paths, and keeps the worktree.**
  `writes` is required: a lane with no declaration would be a second exclusive task that nothing holds back. What a
  lane task writes in other repositories (`seldon cc file`, by path) is outside this repository's merge, as for any
  task.
- **AD-038-R42. A project may declare premises, `dispatch.premises: [{statement, check}]`, that the dispatcher evaluates before every launch (serial, parallel and the lane's), each `check` an opaque command; a false one refuses the launch and prints the premise and its check's output; it is a standing condition: one `dispatch_refused` (reason `project_premise_false`) per episode of the same premises false, the stuck streak, no Issue, and it clears itself on the first pass on which every premise holds.**
  It never touches a running session, and the merge round, redrives and the stuck alarm run earlier in the pass, as
  before. seldon reads no grant: factory's cost manager is the check.
- **AD-038-R43. With `dispatch.hive.mint_command`, the dispatcher (the pass in place, the supervisor for a worktree task) runs it once per launch, outside the session, and puts the token it prints only in the session's environment as `HIVE_TOKEN` with `HIVE_PROJECT` and `HIVE_TASK`; `session_identity` records the identity's name and a 12-character sha256 prefix of the token, never the token; a failed mint is recorded and the session launches without a token; `dispatch.hive.notices_hook` is placed on every launch line as a PostToolUse hook; an inherited `HIVE_TOKEN` never reaches a session.**
  A failed mint does not refuse the launch: a post is context and never read by a gate (factory DN-005 decision 3).
  The board, its tokens and its protocol stay factory's; the mint command is factory's client.
- **AD-038-R44. The session guard: the PreToolUse tool gate refuses any tool call that names a path under `dispatch.guard.deny_paths` or `dispatch.hive.secrets_dir`, by a file tool's path argument (resolved) or by a Bash command's or a search's text (resolved, `~`, `$HOME` and `/private` spellings), before it reads the event store; the paths ride on the hook's own command line (`--deny-path`).**
  It stops a session's ordinary reach and is not a wall: a session runs as the operator's Unix user, so a determined
  process can still read the file. The board's own mint ledger stays factory's second check.
- **AD-038-R45. Every limit the launch line sets is tried by a planted request whenever the limits' fingerprint is new, before any launch, and by `seldon dispatch controls`: each guarded path by a planted `Read` and a planted `Bash cat` fed to the installed hook command, the spend ceiling by the inspector over a planted session at twice its ceiling; one `limits_tried` per fingerprint; a limit that lets its plant through refuses every launch (`limit_control_failed`, a standing condition in the stuck streak) until the limits change and hold.**
  The Network line is recorded as untried, with why: it reaches a session only as `SELDON_NETWORK_ALLOWLIST`, which a
  consumer's fetch helper reads, and seldon enforces no host rule of its own. FAC-31's path-syntax failure cannot
  occur in a rule seldon's launch line writes: its only permission rules are `dispatch.allow`, which refuses anything
  but `Bash(<pattern>)` at load, so the guard is its one path limit, and it is tried, not read.

## 4. What this does not change

- A project with none of the four blocks launches exactly as before; the one visible difference is R45's
  `limits_tried` line, once per fingerprint, in the first launch's record commit (the spend ceiling is set for every
  session, so it is tried for every project).
- FIFO (DN-006 decision 9) among the tasks of each class; no task file can put itself in the lane.
- The per-task band (c4) and the session's stop ceiling (Spend × 1.2).
- `seldon dispatch status` under `max_parallel > 1` (`dispatch_worktree.survey`) shows the planner's view without the
  lane's ordering or c6; the pass itself applies both.
