# SEL-042 ADDENDUM 01: an untracked `uv.lock` in seldon's primary checkout stalled the whole queue for fourteen hours

**Author:** Desktop session (seldon, SLD-2), 2026-11-21 08:20 EST.

## What was found

The dispatcher's pass at 2026-11-21T13:02:21Z refused the queue: `dirty_tree: c7,c17`, `dirty: uv.lock`, `unreconciled: uv.lock: not machine-written governed state (untracked)`. The file was created at 2026-11-20 18:01:38 EST (262,297 bytes) in `/Users/brock/GitHub/seldon/`. seldon is pip-installed and has never carried a `uv.lock`; no seldon task ran that evening. A `dispatch_stuck` event was recorded. The only signal to the operator was a local banner.

## What the Desktop session did

Moved the file, unread and unchanged, to `.seldon/quarantine_uv.lock_2026-11-21` (gitignored runtime state) so the queue can run. Nothing was deleted.

## Added to this task (Part B's share covers it; Parts unchanged)

1. Find what wrote it: which process ran `uv` with seldon's primary checkout as its working directory or project at 18:01 EST on 2026-11-20 (the other projects' dispatch logs and session logs for that minute; hazbrief's gate is `uv run pytest ...`; a new project was created that day). Report the writer. If it is seldon's own code launching a consumer's command in the wrong directory, fix it with a test. If it is another project's session, the RESULT says which and the return to that project reports it.
2. Say, with the evidence, whether the file should exist (then it is tracked or ignored by ruling) or should not (then the writer is the defect). Delete the quarantined copy only after that is settled.
3. Do not change what counts as dirt. A stray file stopping the queue is the designed behaviour; the defect is that it took fourteen hours and a person to see it. Record how long the alarm stood and where it was shown, for SEL-044's portfolio brief to carry.
