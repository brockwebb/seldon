# SEL-060 Part A: is recall used? The baseline, counted from the sessions' own logs

**Produced by:** `seldon qc recall-audit --out docs/evidence/sel060/part_a_tables.md` (code: `seldon/core/recall_audit.py`),
run 2026-11-27 from the task's worktree against every registered repository's primary checkout. Zero model calls.
**Repositories:** the ONE list, factory's `portfolio.repositories` (`recall.audit.repositories_from`): seldon,
squiddy, hazbrief-mcp, ai-readiness-kg, icsp_notebook, arnold, aacps-ai-policy, critical-thinking-ai, factory.
**Window:** per repository, from its first `recall_listed` record (recall turned on) to the run. Full tables:
`part_a_tables.md`.

## The answer

**Of 2,264 hits handed to 286 dispatched sessions in four repositories, 328 (14.5%) were ever opened, and RESULTs
named 376 (16.6%) as used. 136 of the hits named as used were never opened.** Five repositories were handed nothing:
icsp_notebook and arnold have no dispatch logs (arnold registered 5 tasks with recall and dispatched none), and
aacps-ai-policy, critical-thinking-ai and factory have no `recall:` block, so their 101 logged sessions got no list.

The table that decides Part B is what the task file itself cites:

| hit | handed | opened | used |
|---|---|---|---|
| a RESULT of a task the task file cites | 354 | 155 (43.8%) | 184 (52.0%) |
| a decision record the task file cites | 38 | 24 (63.2%) | 26 (68.4%) |
| a RESULT the task file does not cite | 1,518 | 33 (2.2%) | 58 (3.8%) |
| a decision record it does not cite | 150 | 15 (10.0%) | 24 (16.0%) |
| an Issue (never cited by id) | 184 | 99 (53.8%) | 82 (44.6%) |
| a kept or superseded task | 20 | 2 | 2 |

Two-thirds of what recall handed (1,518 of 2,264) were RESULTs the task did not cite, and sessions opened one in
forty-six of them. The uncited RESULT did no better at any shared-term count (opened 2 to 4%, used 2 to 6%, at
4-7, 8-11 and 12+ shared terms), so no lexical threshold rescues it. Lexical Issues did: opened 33% at 4-7 shared
terms, 63% at 8-11 and 84% at 12 or more. The served arm's hits (475 fused with lexical, 15 alone) were opened twice
and used 8 times. Rank mattered (rank 1 opened 30%, rank 8 9%), as click-through studies predict.

By repository the use rate is hazbrief-mcp 21.7%, seldon 12.1%, squiddy 9.1%, ai-readiness-kg 2.3%. hazbrief's
tasks are long chains citing their predecessors by code, which the lexical arm happens to find.

## How it was counted

- **Handed**: the hit lines of the Recall block in each launch header of `<log_dir>/<stem>.log` (the prompt the
  session actually got; every relaunch's header included).
- **Opened**: a tool call (Read, Bash, Grep, Glob, an Agent prompt; not Write or Edit, whose input is what the
  session wrote, including its own `Recall used:` line) names the hit: a RESULT or task file by name or by a glob
  of at least seven literal characters that matches at most three task files (`2026-11-27_OODA-0*` sweeps
  twenty-four); an Issue by its id prefix; a decision record by its id or its register file. Reading a decision's
  design note is counted apart (27), because sessions read the governing notes anyway.
- **Used**: the newest `recall_used` record, or the RESULT on disk when the dispatcher has not read it.
- **Cited**: the task file contains the hit's task code (`SEL-055`) or record id (`AD-031-R3`).

Two earlier counts of this audit were wrong and are not used: the first counted any glob (91.6% opened, because
`find . -not -path "./.git/*"` matched every file); the second counted Write and Edit inputs (20.0%), so a RESULT
listing the hits it used counted them as opened.

## Limits

- Opening is a lower bound on looking: a session can act on a hit's one-line headline without opening it. That is
  the 136 "used, never opened", and why the RESULT's line is kept beside the log's count (Joachims et al. 2005:
  a click is relative evidence of relevance, biased by position and presentation).
- A Bash `cat > file` naming a hit counts as an open; telling it from a read would need a shell parser. Rare.
- The window differs per repository (seldon from 2026-10-20, arnold's first listing 2026-11-09).
