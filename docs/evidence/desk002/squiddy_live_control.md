# DESK-002 Part D: the live control in squiddy

**Task:** DESK-002R (3bb19003). **Run:** 2026-10-16, with DESK-002 Parts A and B on seldon main (`0ed91e5`).
**Case:** squiddy DN-048 labels R-207 (register seq 985). Desktop had written the note, the record
`00985_squiddy-r-207_accept.yaml`, the re-rendered `REGISTER.md` and the task SQ-017, and none of them was committed.
Before DESK-002, registering SQ-017 refused with `governing_note_uncommitted` (Issue `5c689098`).

**State found.** `git status --short` in squiddy at `6eee7a7`:

```
 M docs/decisions/REGISTER.md
?? cc_tasks/2026-10-16_SQ-017_dn048_export_ledger_position_arnold_closed.md
?? docs/decisions/register/00985_squiddy-r-207_accept.yaml
?? docs/design/2026-10-16_DN-048_export_records_ledger_position_check_before_compares_prefix.md
```

The task named two more files, `state/prior_art_queries.jsonl` and `governed/ledger/events.jsonl`. Their DN-048
prior-art lines had already been committed by squiddy's standing dispatcher (`8fb1c12`, `af8d395`, `6eee7a7`), so
they were not uncommitted when this ran. The R-207 record's `source.sha256` is DN-048's whole-file digest, and its
`source.text` is the note's text at lines 48 to 54. So it passes DESK-002 Part C's checks as written.

**Command**, run from squiddy's root with seldon main's code (`/opt/anaconda3/bin/seldon`, editable install):

```
seldon cc register cc_tasks/2026-10-16_SQ-017_dn048_export_ledger_position_arnold_closed.md --allow-untracked
```

It exited 0: `Registered: SQ-017 ...`, `id: 174d0337...`, `state: proposed`,
`source_commit: f91b89c32b9ee994f0d8e525c159fc0d19eb31ca`, `event lines committed: 5649775`. It also reported
`governing note(s) to commit with the task: docs/design/2026-10-16_DN-048_...; 1 register file(s) already written to commit`.
The model-lock refresh probe failed (`probe 'fable' failed`), and the command went on with the current lock. That
is unrelated to this control.

**Commits made by the registration** (no hand `git add`):

| commit | files |
|---|---|
| `f91b89c` register: SQ-017 with its governing note DN-048 (task 174d0337) | the task file, DN-048, `00985_squiddy-r-207_accept.yaml`, `REGISTER.md`, `governed/ledger/events.jsonl` (+1), `state/prior_art_queries.jsonl` (+8) |
| `5649775` register: record of SQ-017 (174d0337), 11 lines (artifact_created, link_created) written by its registration | `seldon_events.jsonl` (+11) |

So the note, its R-207 record and `REGISTER.md` went in ONE commit, and the commit gate passed (Part A). The event
store's lines, `governed_sync`'s `link_created` among them, went in the registration's own `register: record` commit
(Part B).

**`git status --short` after:** empty. Branch `main...origin/main`, pushed.

SQ-017 (`174d0337`) was not run. squiddy's own dispatcher launches it.
