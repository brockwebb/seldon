# Consumer filing from squiddy: the seldon-squiddy environment lease serialises every squiddy launch behind any running seldon session and the reverse; 533 minutes waited in REV-001's window and a refusal again on 2026-11-05; the question is whether a session should read seldon at a pinned commit instead

**Repo:** seldon. **Date:** 2026-11-06. **Authored by:** a Desktop session in squiddy (SQ-13), at the operator's direction after he asked why squiddy was "being held up by other things", filed into seldon's queue under AD-036-R12 as a report with the measurement that already exists. No candidacy headers, not a dispatcher candidate; it registers when SEL-023 Part A lands, and until then seldon's Desktop registers it. This filing proposes no fix; it carries REV-001's analysis as the consumer's reading and asks seldon to rule.
**Evidence:** seldon AD-037-R6 (a) and QC-002 (the dispatcher's own premise on every task); seldon `seldon/core/stations.py` lines 7 and 71 (`REFUSED_ENVIRONMENT_IN_FLIGHT`), `:135` (where a task's environment projects are named), `seldon/commands/dispatch.py:2277` (station (a), one refusal per sibling lease); squiddy `squiddy/kit.yaml:65` `environment_packages: [seldon]` with its reason at `:63-64`; squiddy `seldon.yaml:91-103` (`stations.environment_ref: squiddy/kit.yaml#environment_packages`); squiddy REV-001 (2026-10-23) `docs/review/2026-10-23_REV-001/C_throughput.md` row 5 and section 7, and `D_toil.md` section 8 (`environment_in_flight`); squiddy `seldon_events.jsonl` `dispatch_refused` 878dfe5a at 2026-11-05T21:38:54Z, payload `{reason: environment_in_flight, held: {seldon: {holder: dispatcher:HexagonMBP.local:52266, task: null, acquired_at: 2026-11-05T21:38:53Z}}}`; squiddy `logs/squiddy_dispatch.log` lines 17865 to 17872; squiddy `squiddy/kitpass.py:17-24` and `:38-45` (the kit's own `git clone --shared` at a commit, the existing snapshot mechanism).

## What the consumer measured

1. **The coupling, as declared.** squiddy's environment names seldon (`kit.yaml:65`) because squiddy's `.venv` imports seldon as an editable checkout: the `seldon` CLI, the commit hooks, `cc register`, and the dispatcher itself run from `/Users/brock/GitHub/seldon`. AD-037-R6 (a) then puts one premise on every launch in either project: no dispatcher launches while another project's dispatcher holds a lease on a repository its environment names. The reason is one incident: on 2026-10-14 seldon's MODEL-003 merge landed one minute into run 1 of a squiddy kit pass and 28 model-client tests failed with nothing in the pass row saying why (`kit.yaml:63-64`; SQ-015).

2. **The cost, measured by REV-001 (2026-10-23).** `D_toil.md` section 8: six `environment_in_flight` episodes, 81 refused passes, **533.1 minutes** waited, by repository and holder:

   | waiting | holder | from the log | refused passes | minutes |
   |---|---|---|--:|--:|
   | seldon | squiddy SQ-018R | 2026-10-17 14:14 to 15:55, 16:00 to 16:21 | 24 | 121.3 |
   | seldon | squiddy SQ-022 | 2026-10-22 21:52 to 2026-10-23 00:49 | 35 | 177.6 |
   | squiddy | seldon STATION-001 | 2026-10-22 11:58 to 12:54 | 11 | 55.7 |
   | squiddy | seldon ATTR-001 | 2026-10-24 00:27 to cutoff (open) | 11 | 52.1 |
   | squiddy | seldon DESK-002R (event only) | 2026-10-17 01:42 to 02:08 | n/a | 25.5 |
   | squiddy | seldon FRICTION-001 (event only) | 2026-10-17 12:15 to 13:56 | n/a | 100.9 |

   `C_throughput.md` row 5: 22 refused fires in 45.6 hours of log, up to 1.77 hours a week of queue latency, "no" mechanism in the kit, safe "only with a pinned seldon snapshot, never by dropping the lease". Closing at the time: none. No task was filed in either repository.

3. **It fired again on 2026-11-05.** squiddy's dispatcher refused 878dfe5a at 21:38:54Z because seldon's dispatcher had acquired its lease one second earlier (21:38:53Z, `task: null`, SEL-023's launch). The wait this time was under six minutes (the next squiddy pass at 21:44:01Z launched 0b39daec). The episode is small; the mechanism is the one REV-001 measured.

4. **The consumer's reading, from REV-001 section 7, offered as a reading and not a design.** The lease implements readers-writer exclusion (Courtois, Heymans and Parnas, CACM 1971): the squiddy session is a reader of seldon's checkout and a seldon session is a writer, so they are serialised. The incident it answers is a reader observing a write mid-run. The standard answer to that is snapshot isolation (Berenson et al., SIGMOD 1995): the reader reads at a fixed commit, and a concurrent write cannot change what it imports. squiddy's record-pass already does this for the kit itself (`kitpass.py:17-24`, `:38-45`: a `git clone --shared` at a commit on `PYTHONPATH`). The same treatment for seldon, a clone at the HEAD read at launch and recorded in `dispatch_launched`, would remove the wait without dropping the guarantee the lease gives. REV-001 said this; nobody acted on it, and the consumer is not the right party to act on seldon's dispatcher.

5. **What the consumer does not know.** Whether the seldon CLI and hooks a squiddy session calls at run time (not only what it imports) are safe to run from a snapshot that main has moved past; whether seldon's own tooling reads squiddy's checkout in a way the symmetric lease protects; and what else AD-037-R6 (a) guards that REV-001 did not see. Those are seldon's facts.

## What the consumer wants to know back

Whether AD-037-R6 (a)'s lease is the intended permanent design, or whether a session that reads a sibling repository should read it at a pinned commit so that the lease can be narrowed to the cases a snapshot cannot cover. If the latter, squiddy will carry whatever declaration the seldon thread asks of a consumer (a pinned commit in `dispatch_launched`, a `worktree_links` entry, or an environment declaration), and REV-001's 533 minutes is the baseline the change is measured against.
