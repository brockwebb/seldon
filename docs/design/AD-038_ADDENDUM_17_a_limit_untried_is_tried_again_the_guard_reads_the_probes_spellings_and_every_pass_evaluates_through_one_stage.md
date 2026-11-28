# AD-038 ADDENDUM 17: a limit the harness could not try is tried again, the guard reads the spellings the probe got past, and every pass evaluates through one stage

**Date:** 2026-11-28. **Status:** Accepted. Implemented by SEL-062 Parts A and B
(`cc_tasks/2026-11-28_SEL-062_the_dispatchers_limits_passes_and_merge_evidence_hold_what_their_rulings_say.md`), from
REVIEW-001's findings F-05 to F-07, F-09 to F-15, F-17 and F-22
(`docs/reviews/2026-11-28_REVIEW-001_review_4227_changed_lines_of_seldon_code_merged_since_e42c25bc/review.md`).
**Amends:** AD-038-R40 (the lane holds what it declares), R43 (a failed mint's record), R44 (the guard's claim and its
spellings), R45 (an untried control, the fingerprint, the command's state). **New:** AD-038-R46 (one evaluation stage).
**Code:** `seldon/core/controls.py`, `seldon/core/hive.py`, `seldon/core/dispatch.py` (`plan_launches`),
`seldon/core/events.py` (`pass_scope`), `seldon/commands/dispatch.py` (`evaluate_queue`, `pass_alarms`,
`_controls_gate`, `seldon dispatch controls`, `_pass`, `_survey`), `seldon/commands/dispatch_worktree.py`
(`pass_parallel`, `survey`), `seldon/commands/dispatch_lane.py` (`launch_beside`), `seldon/commands/dispatch_gate.py`
(`maybe_run`).
**Tests:** `tests/test_sel062_part_a.py`, `tests/test_sel062_part_b.py`.

## 1. Evidence

Each finding below was read again at this branch's base (`2c0f861`), and each has a test that failed there.

1. **F-05. One slow hook call latched every launch.** `controls.guard_controls` recorded `refused: False` on an
   `OSError` or a `TimeoutExpired`, the same row as a limit that let its plant through. `_controls_gate` tried the
   controls again only when the limits' fingerprint changed. So a hook call over `HOOK_TIMEOUT_S` refused every launch
   until someone edited `seldon.yaml`. `seldon dispatch controls` wrote no state, so running it cleared nothing. The
   fingerprint hashed the launch line's hook command, its deny paths and the spend factor, and not the code that
   enforces them: a change to `refusal()` was never tried.
2. **F-06. The session guard was a substring test.** REVIEW-001's probe ran `controls.refusal` over a guarded
   `/tmp/rv001_probe/vault/secrets`. It allowed three spellings: `cd /tmp/rv001_probe/vault && cat secrets/x`,
   `cat .../sec""rets/x`, and a `Grep` rooted at `.../vault`. R44 says the guard stops "a session's ordinary reach",
   and each of those is ordinary reach.
3. **F-22. A failed mint's stderr was written into the record.** `hive.mint` put the last 300 characters of the mint
   command's stderr into `error`, and `hive.record` copied `error` into `session_identity`, which is committed and
   pushed. A mint command that echoes its minter token on failure would publish it.
4. **F-15, the root of F-07 and F-13. Three pass implementations disagreed.** The serial pass (`dispatch._pass`), the
   parallel pass (`dispatch_worktree.pass_parallel`) and the lane's look (`dispatch_lane.launch_beside`) each build the
   queue by hand. Read at the base:
   - the held alarm (`_held`, SEL-052) was called only by the serial pass (F-07);
   - the parallel pass also passed no `premise_holds` (c13) and no `launch_holds` (c15) to `evaluate`, and ran no
     station (a) premise review;
   - `seldon dispatch status`, serial and parallel, ordered the queue without the lane and applied no lane c6 (F-13).

   No consumer runs `max_parallel > 1` today (seldon, factory, squiddy, hazbrief-mcp and aacps-ai-policy all declare
   1), so none of this has rung on a live queue yet.
5. **F-10. The lane held nothing.** `plan_launches` let a lane candidate `continue` before any `touches_overlap`, and
   dropped running lane rows from what is held. R40 exempts a lane task from exclusive holds only.
6. **F-11. A scheduled gate could start beside a lane session.** In a serial lane project, the claim in flight is the
   in-place claim only, so `GATE.maybe_run` ran while a lane session worked. The parallel pass guards it with
   `not running`.
7. **F-12.** `dispatch_gate.maybe_run`'s docstring says it never raises, but it caught only `ScheduledBusy` and
   `GateConfigError`.
8. **F-17. The event store was read in full many times per pass.** The primary store is 20,250,081 bytes and 14,938
   events. One parse takes 0.10 s on this machine, measured with `read_events` on 2026-11-28. A nothing-eligible
   serial pass parsed it in full more than ten times (the test counts it).
9. **F-09. Lane membership is the task's name.** Every filer here is a session or a person on one operator's machine.
   The only actor a registration records is `--actor`, which is free text. So nothing attests who filed a task, and
   ADDENDUM 16 §4's "no task file can put itself in the lane" does not hold.

## 2. Prior art

### External

- **Complete mediation and least privilege** (Saltzer and Schroeder, "The Protection of Information in Computer
  Systems", Proc. IEEE 63(9), 1975). Complete mediation means every access to every object is checked against the
  authority, not only the access as the checker spells it. A denylist of spellings is not complete mediation.
  Named, not fetched. Applied to R44: the guard is narrowed to what it can claim, and the complete form is named as
  the deferred alternative (§4).
- **Claude Code's sandbox.** code.claude.com/docs/en/sandboxing, read 2026-11-28 through a fetch agent:
  - The sandbox "covers shell commands only". Read, Edit and the other file tools "follow permission rules instead".
  - `sandbox.filesystem.denyRead` denies reads to sandboxed Bash, enforced by macOS Seatbelt.
  - Sandboxed Bash may write only to the working directory, a per-user temp directory and `--add-dir` paths, unless
    `sandbox.filesystem.allowWrite` adds more.
  - Its network goes through a proxy whose `sandbox.network.allowedDomains` "start empty".
  - `allowUnsandboxedCommands: false` removes the `dangerouslyDisableSandbox` retry.
  - `--settings` takes the block per session.

  This is the OS-enforced deny the review names. Not adopted now, for the reasons in §4.
- **Guards on state-machine transitions** (OMG SysML v2 and KerML: "A transition usage can also have a Boolean-valued
  guard expression"; UML and Harel statecharts). Used in AD-034 ADDENDUM 15 for R41. Here it grounds R46's form: one
  stage that every path through the machine passes, not one copy per path.
- **Pipes and filters** (Shaw and Garlan, *Software Architecture*, 1996). A pass is a fixed sequence of filters over
  the queue. Every launch policy reuses them and varies only the last filter. Named, not fetched.
- **Append-only logs and their consistency** (RFC 9162, Certificate Transparency 2.0: "The append-only property of
  each log is achieved using Merkle Trees, which can be used to efficiently prove that a" later log extends an
  earlier one). F-17's reader takes the same position at the cost of one hash: a store whose first N bytes are
  unchanged has been appended to, and only its tail is parsed. Any other change is parsed again in full.
- **Negative testing of an access control** (NIST SP 800-53 Rev. 5 CA-2, CA-8), already R45's grounding. An
  assessment that could not run yields no reading. It is not a failed control. Named, not fetched.
- The library arm:
  - library receipt: query "guard condition refuses a request that names a protected path" | graph seldon-biblio | release seldon_biblio_graph_20261111_sel037_2026-11-11.json sha256:076422bb8382009ff8c0105c7ae07dd9b2f2a86b7ff7fd24b4674e219c6b7b4c | rows doc_omg_sysml_v2_1#b952:373365-373699, doc_omg_sysml_v2_1#b1122:409292-409687, doc_omg_sysml_v2_1#b1132:412287-412403, doc_omg_kerml_1#b5053:794574-794639, doc_omg_kerml_1#b5052:794480-794572, doc_omg_kerml_1#b381:185109-185631, doc_sw_sphinx_needs_2#b565:51156-51249, doc_rfc9162_1#b590:105189-105339, doc_rfc9162_1#b219:36471-36731, doc_rfc9162_1#b129:22879-22969, doc_sw_openfasttrace_ug_reference_xml_tracing_report#b25:4416-4666, doc_sw_openfasttrace_ug_reference_xml_tracing_report#b24:4121-4415, doc_rfc8493_1#b185:31121-31218, doc_nasa_swe_072_1#b249:38769-39127, doc_nasa_swe_072_1#b410:68279-68512, doc_nasa_swe_072_1#b290:46380-47117, doc_sw_openfasttrace_ug_reference_input_format_support#b9:1038-1166, arxiv_2406_14325#b115:62816-63838, xiong2026alma#b456:190099-191767, xiong2026alma#b319:103092-103204, xiong2026alma#b218:87734-87837, doc_sw_openfasttrace_ug_use_cases_delegating_requirement_coverage#meta, doc_sw_openfasttrace_ug_reference_oft_command_line#b55:2900-2928, zhuge2024agentjudge#b326:88025-88085, doc_sw_openfasttrace_ug_oft_api_using_oft_from_java#b44:3937-4062, doc_who_trs1033_annex4_1#b1397:385593-385810, doc_who_trs1033_annex4_1#b1240:346883-347188, doc_who_trs1033_annex4_1#b439:111958-112644, doc_premis_3_0_1#b927:406729-406827, doc_premis_3_0_1#b311:97594-97899, doc_sw_madr_1#b41:4856-4935, doc_sw_openfasttrace_ug_installation_linux#b22:1704-1768, doc_sw_openfasttrace_ug_installation_macos#b17:1253-1317, doc_sw_openfasttrace_ug_use_cases_understanding_and_fixing_broken_requirement_branches#meta
  - library receipt: query "incremental reading of an append-only log from a saved offset" | graph seldon-biblio | release seldon_biblio_graph_20261111_sel037_2026-11-11.json sha256:076422bb8382009ff8c0105c7ae07dd9b2f2a86b7ff7fd24b4674e219c6b7b4c | rows doc_rfc9162_1#b33:9073-9429, doc_rfc9162_1#b508:88439-88469, doc_rfc9162_1#b300:51813-52278, ilyas2022saga#b209:77821-77969, ilyas2022saga#b71:22992-23359, ilyas2022saga#b83:27605-27909, doc_who_trs1033_annex4_1#b1963:514236-514331, doc_who_trs1033_annex4_1#b1137:326375-326390, doc_who_trs1033_annex4_1#b1340:370331-370346, adler2021incremental#meta, doc_omg_sysml_v2_1#b1040:393611-393725, doc_omg_sysml_v2_1#b1560:514193-514273, doc_omg_sysml_v2_1#b955:374283-374948, doc_sw_sphinx_needs_1#b43:735-753, doc_sw_sphinx_needs_2#b43:732-750, doc_sw_openfasttrace_ug_introduction_concepts_and_terms#b31:2491-2783, arxiv_2104_03986#b188:70259-70476, arxiv_2104_03986#b186:69453-69763, arxiv_2104_03986#b220:80329-80662, xiong2026alma#b43:24551-24817, xiong2026alma#b211:87050-87165, xiong2026alma#b224:88212-88271, doc_omg_kerml_1#b166:138897-139168, doc_omg_kerml_1#b3473:654528-655140, doc_omg_kerml_1#b6131:889141-889750, nygard2011adr#b59:6983-6995, doc_nasa_swe_072_1#b533:92448-92559, doc_nasa_swe_072_1#b643:113342-113502, zhuge2024agentjudge#b53:13741-13847, zhuge2024agentjudge#b71:17689-18317, zhuge2024agentjudge#b379:108161-108630, doc_sw_openfasttrace_ug_reference_oft_command_line#b71:3782-3813, doc_sw_openfasttrace_ug_reference_oft_command_line#b34:1803-1877, amodei2016concrete#b278:106943-107141, amodei2016concrete#b301:110564-110728, amodei2016concrete#b289:108745-108892, browning2014doorstop#b53:14046-14462, doc_sw_openfasttrace_ug_use_cases_understanding_and_fixing_broken_requirement_branches#b14:3051-3102, doc_premis_3_0_1#b856:386177-386556, doc_premis_3_0_1#b847:382512-382898, doc_premis_3_0_1#b371:109278-109365, doc_omg_reqif_1_2_1#b878:99607-99741, doc_omg_reqif_1_2_1#b1642:129937-130138
  - library receipt: query "a control that could not run is not a control that failed" | graph seldon-biblio | release seldon_biblio_graph_20261111_sel037_2026-11-11.json sha256:076422bb8382009ff8c0105c7ae07dd9b2f2a86b7ff7fd24b4674e219c6b7b4c | rows zhuge2024agentjudge#b321:87687-87714, zhuge2024agentjudge#b342:88916-89155, zhuge2024agentjudge#b348:89388-90345, amodei2016concrete#b184:92285-92397, amodei2016concrete#b252:102862-102989, amodei2016concrete#b243:101143-101303, doc_nasa_swe_072_1#b836:161113-161221, doc_nasa_swe_072_1#b830:160128-160348, doc_nasa_swe_072_1#b909:170065-170267, niosh_hierarchy_of_controls#b13:773-913, doc_sw_cog_1#b46:6007-6202, doc_omg_kerml_1#b4944:787250-787276, doc_omg_kerml_1#b5048:793598-793813, doc_omg_kerml_1#b3694:705473-706015, doc_sw_madr_1#b27:3904-3919, doc_sw_openfasttrace_2#b53:7604-7620, doc_omg_sysml_v2_1#b2539:672356-672481, doc_omg_sysml_v2_1#b1311:456286-456385, doc_omg_sysml_v2_1#b3947:867766-867894, doc_sw_openfasttrace_ug_installation_linux#b20:1660-1675, doc_who_trs1033_annex4_1#b1299:359972-360744, doc_who_trs1033_annex4_1#b1031:311849-311907, doc_who_trs1033_annex4_1#b1255:350832-351072, doc_sw_openfasttrace_ug_installation_macos#b15:1209-1224, doc_sw_openfasttrace_ug_installation_windows#b11:994-1009, doc_sw_sphinx_needs_1#b1073:19886-19933, doc_sw_cog_2#b7:551-569, doc_sw_openfasttrace_ug_oft_api_using_oft_from_java#b6:608-624, zhang2026rlm#b31:11456-11642, zhang2026rlm#b147:67731-68019, zhang2026rlm#b149:68437-68754, doc_sw_openfasttrace_ug_tool_support_tools_for_authoring_oft_documents#b14:2356-2391, clark2014micropublications#b526:117181-117505, clark2014micropublications#b527:117507-117700, clark2014micropublications#b525:117014-117179, doc_sw_doorstop_2#b37:3962-4004, doc_sw_doorstop_2#b13:2965-3016, doc_sw_doorstop_2#b8:2618-2853

  The first returned SysML v2's guard condition and KerML's ("all Evaluations identified by guard must have result
  value true"). The second returned RFC 9162's append-only property. The third returned nothing on point. The
  operator's `library` graph was searched with the same queries (receipts in `state/prior_art_queries.jsonl`) and held
  nothing on point either.

### Internal

- internal receipt: query "session guard deny path" | repo seldon@2c0f8617e188c5c31e03f1906b45f3bd3af63cff | hits docs/decisions/register/00406_seldon-ad-038-r44_accept.yaml:1, docs/design/AD-038_ADDENDUM_16_a_coordination_lane_project_premises_a_minted_session_identity_and_tried_limits.md:82, docs/decisions/REGISTER.md:9
- internal receipt: query "session guard deny path" | repo squiddy@659c0addc962b71cac63fe674867b8059eafc636 | hits docs/design/2026-11-15_DN-062_the_no_unasked_model_call_check_reads_the_pass_s_own_run.md:91, docs/DECISIONS_INHERITED.md:508, docs/decisions/REGISTER.md:9
- internal receipt: query "session guard deny path" | repo ai-readiness-kg@f3ef4a311c8b10d6c4f7c28ced718302ae2cf6c1 | hits none
- internal receipt: query "session guard deny path" | repo arnold@8c491f6c98586894787f5727560bf37a9d08c2fc | hits none
- internal receipt: query "session guard deny path" | repo icsp_notebook@619179538d53afa65a6390b3feda17d7c30061aa | hits none
- internal receipt: query "session guard deny path" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits none
- internal receipt: query "session guard deny path" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits none
- internal receipt: query "session guard deny path" | repo hazbrief-mcp@b84ca95637b681202b203d3837a42d91fcb5821e | hits none
- internal receipt: query "session guard deny path" | repo aacps-ai-policy@1370530ba3433d24f15fa214505f77fc719504c5 | hits none
- internal receipt: query "session guard deny path" | repo critical-thinking-ai@3d7a1069211ee2eb1a191b3e75c23ccc0a04dd92 | hits none
- internal receipt: query "session guard deny path" | repo factory@25155801f46d3ec2fe3215f244b53f06600db634 | hits none
- internal receipt: query "planted control limits_tried" | repo seldon@2c0f8617e188c5c31e03f1906b45f3bd3af63cff | hits docs/decisions/register/00407_seldon-ad-038-r45_accept.yaml:1, docs/design/AD-038_ADDENDUM_16_a_coordination_lane_project_premises_a_minted_session_identity_and_tried_limits.md:82, docs/decisions/REGISTER.md:9
- internal receipt: query "planted control limits_tried" | repo squiddy@659c0addc962b71cac63fe674867b8059eafc636 | hits none
- internal receipt: query "planted control limits_tried" | repo ai-readiness-kg@f3ef4a311c8b10d6c4f7c28ced718302ae2cf6c1 | hits none
- internal receipt: query "planted control limits_tried" | repo arnold@8c491f6c98586894787f5727560bf37a9d08c2fc | hits none
- internal receipt: query "planted control limits_tried" | repo icsp_notebook@619179538d53afa65a6390b3feda17d7c30061aa | hits none
- internal receipt: query "planted control limits_tried" | repo wintermute@2a78c392f4d998227d2433338ea45aee82c67f1e | hits none
- internal receipt: query "planted control limits_tried" | repo workbench-audit@tree:c03bc86f0e4d7087c6f9cc417ee42ef66f7bc07268d5316448b4344c744b5412 | hits none
- internal receipt: query "planted control limits_tried" | repo hazbrief-mcp@b84ca95637b681202b203d3837a42d91fcb5821e | hits none
- internal receipt: query "planted control limits_tried" | repo aacps-ai-policy@1370530ba3433d24f15fa214505f77fc719504c5 | hits none
- internal receipt: query "planted control limits_tried" | repo critical-thinking-ai@3d7a1069211ee2eb1a191b3e75c23ccc0a04dd92 | hits none
- internal receipt: query "planted control limits_tried" | repo factory@25155801f46d3ec2fe3215f244b53f06600db634 | hits none

What the record held:
- AD-038 ADDENDUM 16, R44 and R45, and their register records (00406, 00407). This addendum amends them.
- squiddy's DN-062, which reads a pass's own run for its no-unasked-model-call check. It is a check on a run, not a
  guard on a path, and is not adopted here.

## 3. Rulings

- **Amends AD-038-R40: A project may declare one coordination lane, `dispatch.coordination_lane: {name_pattern, slots, writes, merge_wait_s}`: a task whose graph name matches `name_pattern` goes first among eligible candidates, always runs in its own worktree under its own supervisor, takes one of `slots` reserved slots and no `max_parallel` slot, and is neither held back by an exclusive task, running or waiting, nor holds one back; its lane's `writes` are its declaration for every other hold, so it waits on a running or waiting non-exclusive task whose declaration overlaps them and, running, holds them; while an exclusive task runs, its holder looks for a lane task at each inspection tick and launches it under the pass lease it already holds; no scheduled full gate starts while a lane session is in flight.**
  F-10 and F-11. Membership by name is a convention within one operator's trust domain, not an attestation (F-09):
  nothing a filer sets is attested here, so ADDENDUM 16 §4's "no task file can put itself in the lane" is withdrawn.
  A task that names itself into the lane is bounded by R41 (it can change only `writes`), by this ruling's overlap
  and by the lane's slots.
- **Amends AD-038-R43: With `dispatch.hive.mint_command`, the dispatcher (the pass in place, the supervisor for a worktree task) runs it once per launch, outside the session, and puts the token it prints only in the session's environment as `HIVE_TOKEN` with `HIVE_PROJECT` and `HIVE_TASK`; `session_identity` records the identity's name and a 12-character sha256 prefix of the token, never the token; a failed mint is recorded by its exit and its stderr's length and 12-character sha256 prefix, never the stderr's text, which goes to the dispatcher's own stderr only; the session launches without a token; `dispatch.hive.notices_hook` is placed on every launch line as a PostToolUse hook; an inherited `HIVE_TOKEN` never reaches a session.**
  F-22. Dropped rather than scanned. A scan would need a secret pattern for a token format that is factory's, and
  any pattern misses some format. The record still matches a failure to its launch, and the text is in the log that
  ran it.
- **Amends AD-038-R44: The session guard: the PreToolUse tool gate refuses a tool call that names a path under `dispatch.guard.deny_paths` or `dispatch.hive.secrets_dir` in any of the spellings it resolves: a file tool's path argument resolved against the call's working directory; a search tool (Grep, Glob, LS) whose root, or an absolute Glob pattern's literal prefix, is the guarded directory or a parent of it; and a Bash command's words after shell quoting is removed (`shlex`), with `~` and environment variables expanded and each relative word resolved against the working directory as the command's own `cd`s change it, the text after a `--flag=`, and the raw text in the `~`, `$HOME` and `/private` spellings; it runs before the tool gate reads the event store, and the paths ride on the hook's own command line (`--deny-path`).**
  This is a denylist of spellings, not complete mediation (Saltzer and Schroeder), and the ruling claims no more.
  A process can still reach the path through a variable it builds, an interpreter's own string, an encoded name or
  a recursive Bash search from a parent. The session runs as the operator's Unix user, and the board's mint ledger
  stays factory's second check. The complete form, an OS-enforced deny, is deferred (§4).
- **Amends AD-038-R45: Every limit the launch line sets is tried by planted requests before any launch when the limits' fingerprint is new or the last try could not run, and by `seldon dispatch controls`, which writes the state a pass reads: each guarded path by a planted `Read`, a planted `Bash cat`, a `cd` to its parent with a relative `cat`, a quote-split `cat` and a `Grep` rooted at its parent, all fed to the installed hook command; the spend ceiling by the inspector over a planted session at twice its ceiling; the fingerprint covers the launch line's hook command, the guarded paths, the spend factor and a sha256 of the code that enforces them (`controls.py`, `dispatch_stations.py`, `stations.py`); one `limits_tried` per fingerprint and outcome; a limit that lets its plant through refuses every launch (`limit_control_failed`, a standing condition in the stuck streak) until the limits change and hold; a plant the harness could not run (an `OSError` or a timeout) is untried, not failed: it refuses the pass it happens on as `limit_control_untried` and is tried again on the next.**
  F-05. An untried limit still refuses its pass (fail-safe defaults: a limit not known to hold is not trusted). It
  no longer latches, because the harness, not the limit, failed. Network stays untried, with the reason R45 gives.
- **AD-038-R46. Every pass (serial and parallel), the lane's look and every status view evaluate the queue through one stage, `dispatch.evaluate_queue` (the band, c13's premise holds, c15's launch holds, the union state, cross-project waits, the OODA's waits, FIFO with the lane first and the lane's c6); every pass runs one alarm stage, `dispatch.pass_alarms` (the last-pass record, the stuck streak, the held alarm), and station (a)'s premise review over each task it would launch; the launch stays two (in place under the pass lease, and a worktree task under its own supervisor), because their finish and lease differ.**
  F-15, F-07 and F-13. These are pipes and filters: the filters are shared, and the launch policy is the variable.
  The serial pass is not folded into the parallel pass. `tests/test_dispatch_serial_transcript.py` holds the serial
  pass to the recorded transcript of the pre-SEL-004 dispatcher, and the in-place launch keeps the pass lease for
  the whole session (AD-037-R17) where a worktree launch hands it to a supervisor. A new station joins the shared
  stages, and `tests/test_sel062_part_b.py` asserts that every pass and status view calls them.

## 4. What this does not change, and what it defers

- **The OS-enforced deny (F-06's complete form) is deferred, not rejected.** It would need two things:
  - sandboxed Bash with `denyRead` on the guarded paths and `allowUnsandboxedCommands: false`;
  - `Read(//<path>/**)` deny rules for the file tools, in the `//` syntax FAC-31 tripped on.

  Turning the sandbox on also confines every dispatched session's Bash writes to its worktree and temp directory.
  `part-complete` writes the PRIMARY checkout's event store (AD-038-R4), and `cc file` writes other repositories.
  Network starts empty, so the sandbox would also become the Network line's first enforced limit (R45's untried
  row). That changes every session on the machine and needs a sandboxed pilot dispatch. An exclusive in-repository
  session cannot launch one. It is PL-018 in `docs/design/seldon_architectural_decisions.md`, with these
  constraints.
- `dispatch.allow` still refuses anything but `Bash(<pattern>)`, so the launch line writes no file-path permission
  rule.
- F-17: the store is parsed once per pass while unchanged, and an append is read as its tail. Callers get their own
  copy of each event, so a caller that mutates what it read changes nothing for the next. No ruling: it is how R46's
  stage reads, not what it decides.
- F-12: `maybe_run` records an unexpected error as `gate_scheduled_error` and prints it. The pass goes on, as R38
  says.
- A project with no lane, no hive and no guard launches exactly as before. The serial transcript is unchanged except
  for the lines this addendum names, if any (the RESULT says which).
