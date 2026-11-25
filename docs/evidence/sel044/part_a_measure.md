# SEL-044 Part A: the twenty-one repositories against `factory/registry.md`

Measured 2026-11-25 at about 06:17Z by `tools/survey.py` (read-only: each `seldon.yaml`, each `seldon_events.jsonl`,
each `.seldon/dispatch_last_pass.json`, one `MATCH (t:ResearchTask) RETURN t.state, count(*)` per graph, and
`~/Library/LaunchAgents/*dispatch*.plist`). The raw rows are `part_a_survey.json`; `tools/table.py` renders the table.
"Open" is the research domain's open ResearchTask states (`seldon.core.artifacts.open_states`), the set
`seldon task list` shows by default.

| repository | graph | tasks (open) | dispatch block | enabled | launchd job | last pass | last event |
|---|---|---|---|---|---|---|---|
| TickBiteRisk | `seldon-tickbiterisk` | 37 (2) | no | - | - | - | 2026-09-04T19:09:03 |
| aacps-ai-policy | `seldon-aacps-ai-policy` | 2 (0) | yes | True | com.brock.aacps-ai-policy-dispatch.plist | 2026-11-25T06:15:58 | 2026-11-01T11:38:41 |
| ai-readiness-kg | `seldon-ai-readiness-kg` | 343 (17) | yes | True | com.brock.airkg-dispatch.plist | 2026-11-22T10:06:20 | 2026-11-24T10:26:22 |
| ai-workflow-design | `seldon-ai-workflow-design` | 80 (1) | no | - | - | - | 2026-09-04T19:08:52 |
| arnold | `seldon-arnold` | 204 (10) | no | - | - | - | 2026-11-21T01:13:28 |
| book_responsible_ai | `seldon-book-responsible-ai` | 15 (0) | no | - | - | - | 2026-09-04T19:08:54 |
| brock_projects | `seldon-brock-projects` | 69 (1) | no | - | - | - | 2026-09-04T19:08:55 |
| census-web-concept-inventory | `seldon-census-web-concept-inventory` | 76 (1) | no | - | - | - | 2026-10-29T15:33:06 |
| factory | `seldon-factory` | 15 (6) | yes | True | com.brock.factory-dispatch.plist | 2026-11-25T06:14:23 | 2026-11-25T06:16:47 |
| federal-survey-concept-mapper | `seldon-federal-survey-concept-mapper` | 49 (27) | no | - | - | - | 2026-09-04T19:08:57 |
| hazbrief-mcp | `seldon-hazbrief-mcp` | 265 (6) | yes | True | com.brock.hazbrief-mcp-dispatch.plist | 2026-11-25T06:13:24 | 2026-11-25T06:13:42 |
| icsp_notebook | `seldon-icsp-notebook` | 286 (23) | no | - | - | - | 2026-10-05T11:55:03 |
| regs-comment-pipeline | `seldon-regs-comment-pipeline` | 7 (0) | no | - | - | - | 2026-09-29T02:06:04 |
| sas_graph_code_conversion | `seldon-sas2graph` | 3 (0) | no | - | - | - | 2026-04-21T02:42:16 |
| seldon | `seldon-seldon-self` | 238 (22) | yes | True | com.brock.seldon-dispatch.plist | 2026-11-25T06:16:49 | 2026-11-25T06:17:05 |
| slosh-pipe | `seldon-slosh-pipe` | 37 (2) | no | - | - | - | 2026-10-22T13:40:23 |
| slosh-pipe-wt-closed | `seldon-slosh-pipe` | 37 (2) | no | - | - | - | 2026-10-19T15:39:18 |
| slosh-pipe-wt-control | `seldon-slosh-pipe` | 37 (2) | no | - | - | - | 2026-10-19T12:29:46 |
| slosh-pipe-wt-metrics | `seldon-slosh-pipe` | 37 (2) | no | - | - | - | 2026-10-18T05:48:42 |
| squiddy | `seldon-squiddy` | 205 (15) | yes | True | com.brock.squiddy-dispatch.plist | 2026-11-25T06:17:16 | 2026-11-24T23:34:43 |
| usai-harness | `seldon-usai-harness` | 51 (0) | no | - | - | - | 2026-09-04T19:09:04 |

Every one of the 21 has a graph that is online and holds ResearchTasks, so every one registers tasks. Six dispatch.
The three `slosh-pipe-wt-*` directories are git worktrees of `slosh-pipe` (`git worktree list`: branches
`p4/closed-tier1`, `p4/control`, `p3e/metrics`) and name the same database, so they are one graph and one repository,
not four: eighteen distinct repositories.

## Differences against `factory/registry.md` (the table is the factory's to correct)

1. **factory, dispatcher column "none" and queue column "none"**: factory has a `dispatch:` block, `enabled: true`, a
   loaded launchd job (`com.brock.factory-dispatch`), a pass at 06:14Z today, and 15 tasks (6 open) in
   `seldon-factory`.
2. **aacps-ai-policy, queue "none yet" and dispatcher "none yet"**: it has a dispatcher (enabled, launchd job loaded,
   a pass at 06:15Z today) and a graph, `seldon-aacps-ai-policy`, with 2 tasks (none open).
3. **ai-readiness-kg, dispatcher "yes (rescan off)"**: `.seldon/DISPATCH_STOP` is present, so no pass has dispatched
   anything since 2026-11-22T10:06Z. The dispatcher is stopped, not only its rescan.
4. **arnold, queue "KG-001", dispatcher "launchd jobs"**: arnold's tasks are a seldon graph, `seldon-arnold`, with 204
   tasks (10 open); it has no `dispatch:` block, so no seldon dispatcher (its launchd jobs are its own, such as
   `com.arnold.seldon-audit`).
5. **icsp_notebook, queue "manifest"**: it also has a seldon graph, `seldon-icsp-notebook`, with 286 tasks (23 open),
   last event 2026-10-05.
6. **ai-readiness-kg and seldon, queue "seldon graph"**: each has its own graph (`seldon-ai-readiness-kg`,
   `seldon-seldon-self`); "seldon graph" does not say which. hazbrief-mcp's row names its database, the others do not.
7. **authoring (planned)**: there is no directory with a seldon.yaml for it yet. The row is correct as "planned"; a
   portfolio declaration cannot list it until it exists, and the brief would show it as unreadable.
8. **Repositories with a seldon graph that the table omits** (ten, plus the three slosh-pipe worktrees): TickBiteRisk,
   ai-workflow-design, book_responsible_ai, brock_projects, census-web-concept-inventory, federal-survey-concept-mapper
   (27 open), regs-comment-pipeline, sas_graph_code_conversion, slosh-pipe, usai-harness. None dispatches. Their last
   events run from 2026-04-21 (sas_graph_code_conversion) to 2026-10-29 (census-web-concept-inventory); eight of them
   have been silent since 2026-10-05 or earlier. Whether each belongs in the portfolio is the factory's call. The
   brief costs one graph read for each one listed (Part D).
