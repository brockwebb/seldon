# Filing from factory: declare the Hive in seldon's dispatch block, so its sessions get an identity and the notices hook

**Kind:** filing
**Filed by:** factory
**Date:** 2026-11-27
**Reporter:** factory FAC-41 (`factory/cc_tasks/2026-11-27_FAC-41_the_hive_is_in_every_dispatched_session_and_a_request_from_one_project_is_answered_by_another.md`),
under factory DN-005 decision 2 and its ADDENDUM 01; seldon AD-038-R43 and R44 (SEL-054), which built what this uses.
**Spend:** est. 0.1M tokens. Basis: one configuration block and one `seldon dispatch controls` run; no model calls of its own.
**Network:** none

## What is already in place, and what is seldon's

The Hive is the factory's board on this machine (Msgboard on 127.0.0.1:8766, factory F-046). Since FAC-41:

- the `hive` skill is linked for every project at `~/.claude/skills/hive` (it says when to ask, and that a post is
  another agent's statement, never an instruction), and the client is at a stable path,
  `/Users/brock/GitHub/factory/scripts/hive.py`;
- seldon's dispatcher mints one board identity per session at launch, puts it in the session's environment as
  `HIVE_TOKEN`, places the notices hook on the launch line, and guards the board's secrets, for every project that
  declares `dispatch.hive` (seldon AD-038-R43, R44).

Nothing was written into seldon's tree. The one thing only seldon can do is declare the block. Without it, seldon's sessions
can still ask the Hive (the client mints an identity itself), but answers never reach them at their next tool call,
and requests addressed to seldon never reach the start of its sessions.

A session that never needs the Hive pays nothing for it: the hook exits in about 0.2 s with no network call and no
output when there is nothing for the session, and a failed mint never stops a launch (a post is context, never a
gate).

## Part A: declare it

1. First: `grep -q "def mint" /Users/brock/GitHub/factory/scripts/hive.py`. If it fails, factory FAC-41 has not merged
   yet: stop and say so in the RESULT, changing nothing.
2. In `seldon.yaml`, under `dispatch:`, add exactly:

       hive:
         mint_command: /opt/anaconda3/bin/python /Users/brock/GitHub/factory/scripts/hive.py mint
         notices_hook: /opt/anaconda3/bin/python /Users/brock/GitHub/factory/scripts/hive.py notices --hook
         secrets_dir: ~/.factory/hive/secrets

   with a comment citing this filing and seldon AD-038-R43.
3. If `.claude/settings.json` in this repository carries a PostToolUse hook running `hive.py notices`, remove it (the
   launch line places it; placed twice, it would deliver twice).
4. Run `seldon dispatch controls` and keep its output in the RESULT: the guard's two plants on
   `~/.factory/hive/secrets` must be `held`.

What NOT to do: do not copy the client, the skill or any token into this repository; do not add the secrets path to
any other configuration.

Acceptance:
- `check: sh -c "grep -q 'hive.py mint' seldon.yaml"` passes.
- `check: seldon dispatch controls` passes.
