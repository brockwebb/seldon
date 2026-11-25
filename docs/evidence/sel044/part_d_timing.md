# SEL-044 Part D: the cost of reading

Measured 2026-11-25 at about 06:33Z with the branch's code (`PYTHONPATH` = the SEL-044 worktree), from a scratch
portfolio project at `/tmp/sel044/port` whose `portfolio.repositories` lists the nine rows of `factory/registry.md` by
absolute path (`tools/real_nine.py`; factory itself was read, not written). `authoring` has no directory yet and is
shown unreadable, as AD-038-R33 requires.

| run | repositories | `max_workers` | read (in the brief's header) | whole command, interpreter start included |
|---|---|---|---|---|
| 1 | 9 | 8 (default) | 1.8 s | 2.61 s |
| 2 | 9 | 8 | 1.9 s | 2.81 s |
| 3 | 9 | 8 | 1.8 s | 2.70 s |
| 4 | 9 | 8 | 1.9 s | 2.76 s |
| 5 | 9 | 1 (serial) | 2.2 s | 3.03 s |
| 6 | 9 | 1 (serial) | 2.1 s | 2.93 s |
| 7 | 18 (every distinct repository, `tools/real_all.py`) | 8 | 2.3 s | 3.04 s |

**Verdict:** `go --portfolio --brief` over the real nine takes under 3 s, a tenth of the thirty-second budget, so
nothing was fixed and no cache was added. Listing all eighteen repositories costs 3 s.

**What the time is.** Most of it is parsing the event stores: about 110 MB of JSONL across the eighteen (seldon 19 MB,
ai-readiness-kg 28 MB, arnold 16 MB, hazbrief-mcp 14 MB, squiddy 11 MB). The read already runs one reader per
repository side by side (AD-038-R35), and that saves only 0.2 to 0.3 s against a serial read: JSON parsing holds
Python's GIL, so threads overlap only the graph queries and file reads. If the stores grow tenfold and the brief
nears thirty seconds, the next step is a process pool or a line prefilter on the few event types the brief reads.
Neither is needed now.

**Counts against each repository's own list** (`tools/real_counts.py`, output `part_d_counts_vs_task_list.txt`): for
all eighteen repositories, the brief's open count and its task ids equal what `seldon task list`, run in that
repository straight after, prints (`same_ids=True` on 18 of 18). The same file counts gate records: only factory has a
record with `wall_seconds` (1). seldon (3), squiddy (8) and hazbrief-mcp (1) have only pre-SEL-043 records, so the
brief shows `no wall-clock gate records` for them (ADDENDUM 01 item 2) and does not fill them in from monotonic
seconds.

The brief as it rendered over the nine is `part_d_brief_real_nine.txt`.
