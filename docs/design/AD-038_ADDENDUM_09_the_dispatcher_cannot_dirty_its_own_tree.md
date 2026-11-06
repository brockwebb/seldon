# AD-038 ADDENDUM 09: the dispatcher cannot dirty its own tree: the rotated log is ignored, and a filing left untracked is committed by the pass

**Date:** 2026-11-06. **Status:** Accepted. Implemented by SEL-025
(`cc_tasks/2026-11-06_SEL-025_the_dispatcher_cannot_dirty_its_own_tree_log_rotation_and_a_filing_left_untracked.md`).
**Amends:** AD-038-R1's class table (one class added, `filing`). Two new rulings.
**Code:** `scripts/jobs/seldon_dispatch.sh` (rotation and retention); `.gitignore` (`logs/**`);
`seldon/core/reconcile.py` (`FILING_DIR`, `is_filing_text`, `filing_path`, the `filing` class, `_filing_groups`);
`seldon/commands/dispatch.py` (`_reconcile` prints `filing_committed:`).
**Tests:** `tests/test_sel025_dispatcher_cannot_dirty_its_own_tree.py`.

## 1. Evidence

1. **Three days refused on c7.** seldon's queue was refused `dirty_tree` on every pass from 2026-11-04 02:19Z to
   2026-11-06 12:55Z, with SEL-023 and SEL-024 waiting. Both untracked paths were the machine's own writes.
2. **The rotated log.** `scripts/jobs/seldon_dispatch.sh` rotated with `mv "$LOG" "$LOG.<stamp>"`, writing
   `logs/seldon_dispatch.log.20261104T021957Z`. `.gitignore`'s `*.log` does not match a name whose last suffix is the
   stamp. It was the second time; the first (2026-10-28) was moved by hand under `logs/dispatch/`.
3. **The unregistered filing.** `cc_tasks/2026-11-02_FAC-03_filing_result_filename_convention_mismatch.md` was written
   into seldon by a dispatched factory session under AD-036-R12. It carried `**Status:** proposed (consumer filing; no
   dispatch headers. ...)` and no `**Kind:**` header (SEL-023 A came later). The reconciler's `task_files` class admits
   registered files only, so the filing sat as dirt and refused the queue that would answer it.
4. **Each time a person fixed it.** A Desktop moved or committed the file by hand. The operator runs nothing by hand.

## 2. Prior art

- **Rotation that keeps the extension last.** logrotate(8), the `extension` directive: "Log files with ext extension
  can keep it after the rotation", so a rotated `foo.log` stays matchable by `*.log`; with `dateext` the stamp goes
  before the extension. Adopted: the rotated name is `<base>.<stamp>.log`, under `olddir`'s analogue
  (`logs/dispatch/`).
- **Ignore patterns match the name's end as written.** gitignore(5): a pattern without a slash matches the basename by
  `fnmatch(3)`, so `*.log` matches `x.log` and not `x.log.20261104T021957Z`; a pattern with a trailing `/**` matches
  everything inside a directory. Adopted: `logs/**`, so any future log name the machine writes there is ignored
  whatever its suffix.
- **The reconciler repairs drift it wrote** (OpenGitOps principle 4, already AD-038-R1's ground). Adopted unchanged:
  a filing is one more class of machine-written state the pass commits before c7.

These sources are cited by their published names and were not fetched (Network: none beyond git).

## 3. Rulings

- **AD-038-R22. The dispatch wrapper's rotated log keeps `.log` last and is ignored.** The wrapper rotates its log
  to `logs/dispatch/<base>.<UTC stamp>.log` and its retention deletes only that name (and the old name, until it ages
  out). seldon's `.gitignore` ignores `logs/**`: no log the machine writes under `logs/` can make the tree dirty.
- **AD-038-R23. The pass commits a consumer filing it finds untracked.** An untracked `cc_tasks/<name>.md` whose header
  block declares `**Kind:** filing`, or whose `**Status:**` names a consumer filing, and an untracked addendum to such
  a file, are the reconciler's `filing` class. Each filing is committed alone, path-limited, through the hooks, as
  `dispatcher: filing: <basename>`, and the pass prints `filing_committed:` with the path and commit. Any other
  untracked path under a governed directory is still dirt, refuses on c7 and is named on the pass line.

## 4. Details

1. **Why only the header block.** A task that discusses a consumer filing in its body is not one; `is_filing_text`
   reads the header block as every other header reader does (AD-038-R14).
2. **Why directly under `cc_tasks/`.** AD-036-R12 files into that directory; a nested file is not a filing.
3. **Why a tracked filing edited is not committed.** Only the untracked file is the filer's unfinished write; an edit
   to a committed filing is someone's change, which c7 names.
4. **What the commit does not do.** It does not register the filing. A filing with `**Kind:** filing` registers
   without candidacy headers (SEL-023 A) by whoever answers it; one without the header (FAC-03's form) is retagged
   with `seldon task update --kind filing` after registration. Committing makes it tracked, which is what both need.
5. **The other projects that run this wrapper** (`seldon dispatch adopt`, AD-038-R11) get the new rotation name from
   the same script. A project whose `.gitignore` has `*.log` now ignores the rotation; one without it needs its own
   ignore, which is that project's rule to add.
