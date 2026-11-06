# Consumer filing from squiddy: `seldon verify` raises KeyError 'record_hash' in a worktree that holds pending register records

**Repo:** seldon. **Date:** 2026-11-06. **Authored by:** squiddy SQ-124's dispatched session (worktree `cosmic-launching-cray`, commit `6fe9a91b`), filed under AD-036-R12 as a report of what the consumer met. No candidacy headers, not a dispatcher candidate. This filing proposes no fix; the seldon thread decides what changes.
**Evidence:** squiddy `docs/decisions/register/pending/00001_07aae02fd4b854df_squiddy-r-251_accept.yaml`, `00002_1bc1ef648900da9a_squiddy-r-252_accept.yaml`, `00003_d4ace9471685b533_squiddy-r-237_amend.yaml` on branch `worktree-cosmic-launching-cray`, each written by `seldon decision accept|amend` and committed through the hooks.
**Kind:** filing
**Filed by:** squiddy

## What the consumer observed

1. In the SQ-124 worktree, after committing three pending register records (two `accept`, one `amend` of the numbered `squiddy:R-237`) with the design note that labels them, `seldon verify` exits with a traceback instead of a report:

       File "seldon/commands/verify.py", line 246, in check_decisions
         if have.get(rec.id) != (rec.last_hash, rec.status):
       File "seldon/core/decisions.py", line 772, in last_hash
         return self.events[-1]["record_hash"]
       KeyError: 'record_hash'

2. None of the three pending YAML files carries `record_hash` (`grep -c record_hash` is 0 on each); every numbered record under `docs/decisions/register/` does. `Record.last_hash` reads `events[-1]["record_hash"]` unconditionally.
3. The pending form is the documented branch path: `seldon decision number` says pending records are "written on a branch" and numbered by the dispatcher at merge, and the commit gate (AD-033-R2) refused the note until the records were staged. squiddy SQ-036 (`f5d84e28`) committed a pending amend the same way.
4. The commit gate and `seldon prior-art verify` worked; only `seldon verify`'s decision-register projection step raised. Every other check's result was not printed, because the exception ended the command.

## What the consumer wants to know back

Whether `seldon verify` is meant to run in a worktree with pending records (and if so, what it reports for them), or is meant to run only after numbering. Return path per AD-036-R16: a task file in `/Users/brock/GitHub/squiddy/cc_tasks/` only if squiddy has something to do.
