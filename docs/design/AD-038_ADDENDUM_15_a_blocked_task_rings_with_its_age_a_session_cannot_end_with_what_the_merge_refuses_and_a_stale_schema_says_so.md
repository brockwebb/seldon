# AD-038 ADDENDUM 15: a task blocked on a person rings with its age, a session cannot end with what the merge refuses, a skipped link is said, and a stale tool schema says so

**Date:** 2026-11-26. **Status:** Accepted. Implemented by SEL-052 Parts A and B
(`cc_tasks/2026-11-26_SEL-052_what_factory_reported_this_week_is_answered.md`), from factory's filings
`cc_tasks/2026-11-24_filing_from_factory_a_hold_that_waits_on_a_person_tells_nobody.md`,
`cc_tasks/2026-11-25_filing_from_factory_a_declared_worktree_link_to_a_tracked_directory_is_skipped_without_a_word.md`
and `cc_tasks/2026-11-26_filing_from_factory_a_return_task_waited_on_a_filing_that_never_runs_...md` (item 3), and the
factory coordinator's CTAI-006R observation.
**Extends:** the stuck alarm (ai-readiness-kg's ADDENDUM_01 decision 6b; `dispatch_stuck`) to blocked tasks, which are
not candidates; the Stop gate of FRICTION-002 Part C with the merge round's own refusal; AD-038-R3 (every tool runs
fresh) with what a fresh child can see that its server cannot. Four new rulings, AD-038-R36 to R39.
**Code:** `seldon/core/dispatch.py` (`advance_held`, `held_remedy`, `held_alarm_after_s`, `held_repeat_s`);
`seldon/commands/dispatch.py` (`_held`, `_blocked_tasks`); `seldon/core/stations.py` (`stop_gate`, `dirt`);
`seldon/commands/dispatch_stations.py` (`_session_dirt`); `seldon/core/worktree.py` (`link_report`);
`seldon/commands/dispatch_worktree.py` (`name_worktree`); `seldon/commands/mcp_call.py` (`stale_schema_note`).
**Tests:** `tests/test_sel052_held_alarm.py`, `tests/test_sel052_stop_gate_dirt.py`,
`tests/test_sel052_worktree_link_skip.py`, `tests/test_sel052_mcp_stale_schema.py`.

## 1. Evidence

1. **A blocked task rang once, at its finish, and never again.** factory FAC-06 (`b62cd550`) was `merge_blocked` from
   2026-11-14 to 2026-11-24. The finish ran `notify` once with the outcome; the stuck alarm counts refused candidates,
   and a blocked task is not one, so the passes that followed were clean and silent. hazbrief's account of
   2026-11-23 names three more stalls that waited on a person.
2. **A green session was blocked for one untracked directory.** critical-thinking-ai CTAI-006R: all five Parts passed;
   the session ended with `graphs/critical-thinking-evidence/archive:inbox/` (a `.gitkeep`) untracked in its worktree;
   the merge round refused it as `uncommitted_changes` at 2026-11-26T22:55:16Z; a person redrove it at 23:15:18Z, and
   a second session deleted the directory and merged in 3 minutes 15 seconds.
3. **A declared link was skipped without a word.** factory declares `dispatch.worktree_links: [.env, corpus/inbox]`
   and tracks `corpus/inbox/.gitkeep`, so every checkout creates the directory and `worktree.link` skipped it;
   FAC-06 and FAC-06R each found an empty real directory.
4. **A tool parameter the server did not know was dropped.** `seldon_go(portfolio=true)` from factory's Desktop on
   2026-11-26 answered as `seldon_go(brief=true)`: the client had been served the schema the long-lived server
   registered at its start, before SEL-044 added `portfolio`. The child runs the checkout's code (AD-038-R3) but
   receives only the arguments the old schema carries. The portfolio brief itself, read on 2026-11-27 through the CLI:
   2,983 characters, 9 repositories, 2.3 s.

## 2. Prior art

### External

- **Alert on a symptom a person must act on** (Beyer et al., *Site Reliability Engineering*, O'Reilly 2016, ch. 6
  "Monitoring Distributed Systems": every page should be actionable and require a person). Named, not fetched. Adopted
  for R36: the ring is raised only for a state the dispatcher will not clear by itself, and it says what clears it.
- **Re-notification of an unacknowledged alert on an interval** (Nagios `notification_interval`; Prometheus
  Alertmanager `repeat_interval`, default 4 h). Named from their documentation, not fetched here. Adopted for R36's
  `held_repeat_s`, with a default of one day.
- **Fail at the station that can fix it** (jidoka; the Stop hook as a completion gate, FRICTION-002's own prior art,
  `docs/research/2026-10-17_vendor_survey_codex_claude_code.html` section 1). Adopted for R37.
- The library arm returned nothing on point:
  - library receipt: query "alerting on symptoms that require human action" | graph seldon-biblio | release seldon_biblio_graph_20261111_sel037_2026-11-11.json sha256:076422bb8382009ff8c0105c7ae07dd9b2f2a86b7ff7fd24b4674e219c6b7b4c | rows doc_who_trs1033_annex4_1#b1119:322562-322589, doc_who_trs1033_annex4_1#b1097:320938-321025, doc_who_trs1033_annex4_1#b481:127457-128339, doc_omg_sysml_v2_1#b1029:390973-391382, doc_omg_sysml_v2_1#b899:360964-361163, doc_omg_sysml_v2_1#b892:359447-359815, doc_nasa_swe_072_1#b417:69603-70010, doc_nasa_swe_072_1#b826:159435-159970, doc_nasa_swe_072_1#b358:56980-57085, zhuge2024agentjudge#b75:19104-20029, zhuge2024agentjudge#b42:12215-12848, zhuge2024agentjudge#b249:64948-65202, amodei2016concrete#b108:59367-59954, amodei2016concrete#b114:64460-64924, amodei2016concrete#b22:10013-11220, liang2026skillnet#b37:11364-11512, liang2026skillnet#b208:89656-90137, liang2026skillnet#b243:104913-105246, doc_omg_kerml_1#b5381:811546-811672, doc_omg_kerml_1#b3209:585710-585796, doc_omg_kerml_1#b5057:795241-795492, doc_sw_requiem_1#b33:2443-2497, doc_sw_sphinx_needs_2#b78:3441-3628, xiong2026alma#b321:103283-103343, xiong2026alma#b179:72281-72558, xiong2026alma#b332:105346-105419, gotel1994traceability#b128:43942-44506, gotel1994traceability#b114:38376-39079, gotel1994traceability#b95:31086-31321, doc_sw_openfasttrace_ug_use_cases_writing_a_specification#b33:4563-4820, doc_sw_sphinx_needs_1#b2254:43040-43452, fuchss2025lissa#b178:72211-72565, fuchss2025lissa#b78:23766-24120, fuchss2025lissa#b199:77846-78125, doc_omg_reqif_1_2_1#b1238:113885-113937, doc_omg_reqif_1_2_1#b186:61175-61476, doc_premis_3_0_1#b856:386177-386556, doc_premis_3_0_1#b795:366817-367760, doc_premis_3_0_1#b809:373085-373172, clark2014micropublications#b521:116411-116539, clark2014micropublications#b325:78047-78109, ilyas2023growing#b69:23386-24570, ilyas2023growing#b101:36412-36862, ilyas2023growing#b29:7239-7547, aaai_v40i44_41105#b55:18607-18771, nasa_oig_ig_12_012#b40:14221-14238, nasa_oig_ig_12_012#b279:81839-82053

### Internal

- internal receipt: query "blocked task notify" | repo factory@2df06838aa7150aae0eddad71b9f8ae4ab850759 | hits docs/architecture.md:54, docs/2026-11-13_hive_prior_art_CLAIM_CHECK.md:110, docs/gaps.md:6
- internal receipt: query "hooksPath worktree" | repo seldon@3f84b3e2a9abe09a4e83342b8689b108ed60d009 | hits docs/decisions/register/00321_seldon-ad-034-r14_accept.yaml:1, docs/design/AD-034_ADDENDUM_07_session_links_worktree_hook_default_part.md:3, docs/design/AD-034_ADDENDUM_07_session_links_worktree_hook_default_part.md:51

What the record held: factory's `docs/gaps.md` G-39 states the need (a hold rings a person); AD-034 ADDENDUM 07 is
where a session's links and the worktree's hook pointing were decided, and its links are the paths the Stop gate's
dirt read excludes.

## 3. Rulings

- **AD-038-R36. A task in `blocked` rings `notify` (outcome `held`) with its stored block reason, its age since it was blocked and the command that clears it, once it has been blocked `dispatch.held_alarm_after_s` (default 900 s), and again every `dispatch.held_repeat_s` (default 86400 s; 0 rings once) while it stays blocked; each ring is one `dispatch_held` event.**
  Read every pass after the auto-redrive (AD-038-R2), so what is still blocked waits on a person; independent of a
  claim in flight. The age runs from the task's last move into `blocked` in the event store. Both defaults have no
  measured basis and say so in `seldon.yaml`.
- **AD-038-R37. The Stop gate reads the merge round's own refusal in the session's worktree: a path `worktree.dirty_paths` returns (minus the launch's links) fails the gate as a check would, under the same ceiling and no-progress rules, whether or not a Part was declared.**
  So the session that left a stray path commits or removes it, and the merge round's `uncommitted_changes` is left
  for what a session could not have fixed. Not judged outside a branch worktree.
- **AD-038-R38. A declared `worktree_links` entry that is not linked because the worktree already has the path is recorded on `dispatch_worktree_named` as `links_skipped` with its reason, and when the repository tracks something at or under it (`tracked_in_checkout`) the launch prints the remedy.**
  The remedy for a local directory shared with every worktree: untrack it and gitignore it as `/<path>` with no
  trailing slash, since a `dir/` pattern does not match the link and git would list its parent untracked. A path the
  primary lacks is the documented skip and is not recorded.
- **AD-038-R39. A tool answer names every parameter of the checkout's tool that the server did not send, with the remedy (restart the server), because the schema a client is served is the one the server registered when it started.**
  The child cannot change the client's schema; it can say that a parameter was dropped instead of answering as if the
  default had been asked for.
