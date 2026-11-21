# AD-038 ADDENDUM 13: a file name the file system cannot take is a refusal, and the OODA knowledge source runs nothing outside its worktree

**Date:** 2026-11-21. **Status:** Accepted. Implemented by SEL-042 Part E and ADDENDUM 01
(`cc_tasks/2026-11-21_SEL-042_a_stopped_session_is_never_merged_or_completed_the_merge_round_cannot_refuse_itself_and_verify_reads_pending_records.md`),
from hazbrief-mcp's filing `1639fa20` (2026-11-19) and the stray `uv.lock` Desktop found in seldon's primary checkout
on 2026-11-21. **Extends:** AD-038-R20 and R26 (`cc file` writes, commits and registers, or files an addendum, in one
call; a refusal writes nothing) to the file system's name limit; AD-038-R16 (the OODA as a knowledge source) with the
boundary its prompt did not state. Two new rulings, AD-038-R30 and R31.
**Code:** `seldon/core/filing.py` (`name_limit`, `addendum_slug_room`, `name_refusal`, `file_task`, `file_addendum`);
`seldon/core/returns.py` (`write_return`); `seldon/commands/cc.py` (`stem_room_warning` at registration);
`seldon/core/ooda.py` (`prompt`).
**Tests:** `tests/test_sel042_verify_pending_and_name_limit.py`; `tests/test_sel042_ooda_boundary.py`.

## 1. Evidence

1. **A long name was a traceback.** Filing an addendum whose name exceeded 255 characters raised
   `OSError: File name too long` from `filing.py` (the write in `file_addendum`). An addendum's name is its task's
   stem, `_ADDENDUM_NN_`, a slug and `.md`; HB-207's stem is 153 bytes, so 86 bytes are left for the slug.
2. **The file system counts characters, not bytes, on this machine.** `pathconf(PC_NAME_MAX)` is 255 on APFS; a
   256-byte ASCII name is refused, and a 256-byte name of 255 characters with one two-byte `é` is written
   (`tests/test_sel042_verify_pending_and_name_limit.py`, measured 2026-11-21). ext4's limit is 255 bytes. A repository
   is cloned on both.
3. **The OODA wrote into seldon's primary checkout.** At 23:01:36Z on 2026-11-20 the OODA knowledge source the
   dispatcher launched in hazbrief-mcp on HB-212 (session `a829d9a0`, worktree `wiggly-giggling-pine`), checking the
   addendum it had just written for HB-213, ran `cd ../../../../seldon && uv run --quiet python -c "...
   addendum_header_refusal..."`. `uv run` in a directory holding a `pyproject.toml` locks and syncs that project: it
   wrote `uv.lock` (262,297 bytes, mtime 23:01:38Z, `seldon` locked as `editable = "."`) and `.venv/` in seldon's
   checkout. seldon is pip-installed and has never carried a `uv.lock`; `.venv` is gitignored, `uv.lock` is not. Every
   seldon pass from then until 12:57:41Z on 2026-11-21 had no candidate (`nothing eligible ... 0 candidate(s)`), and c7
   is read only for a candidate, so nothing reported the dirt for fourteen hours. SEL-041 was registered at 12:57:41Z;
   the next pass (13:02:21Z) refused it `dirty_tree` (`dirty: uv.lock`), recorded `dispatch_stuck` and sent the local
   banner, and Desktop's move of the file cleared it before the pass at 13:07:32Z. The full trace is in
   `docs/evidence/sel042/uv_lock_writer.md`.

## 2. Prior art

### External

- **POSIX `NAME_MAX` and `pathconf(_PC_NAME_MAX)`** (IEEE Std 1003.1, `<limits.h>` and `fpathconf`): the longest name
  a directory's file system takes, in bytes, read per directory because it varies by volume. Adopted: the limit is
  read, not assumed, and counted in UTF-8 bytes, the stricter of APFS's characters and ext4's bytes, so a name that is
  accepted here is accepted in every clone. Named, not fetched. The library arm
  (`"file name length limit NAME_MAX"`, 2026-11-21) returned only unrelated rows.
- **uv's project discovery** (docs.astral.sh/uv, "Running commands" and "Locking and syncing": `uv run` "ensures the
  project environment is up to date", creating `uv.lock` and `.venv` in the project the working directory belongs to).
  Named, not fetched; it is what evidence 3 observed.

### Internal

- internal receipt: query "File name too long" | repo seldon@6a74a6a82c5c73c7f40fc91952bfc9f0d46b477f | hits docs/decisions/register/00010_seldon-ad-021_accept.yaml:1, docs/design/AD-034_ADDENDUM_08_the_merge_requires_the_declared_pass_record.md:58, docs/decisions/REGISTER.md:9

What the record held: AD-038-R20's contract (a refused filing leaves the tree as it was) and SEL-024's own `File name
too long` (a YAML text passed where a path was expected), which is a different cause. Nothing bounded a task's name.

## 3. Rulings

- **AD-038-R30. A task file, an addendum or a return whose name is longer, in UTF-8 bytes, than the file system's limit for its directory (`pathconf(PC_NAME_MAX)`) is refused `name_too_long` before anything is written, the refusal stating the name's length, the limit and the bytes left for the slug; registration warns `addendum_slug_room` when a task's stem leaves fewer than `filings.addendum_slug_warn_bytes` (60, a first value) for an addendum's slug.**
  The warning is not a refusal: the task's own name fits. 60 is a first value, not a measurement: room for a ten-word
  slug, against HB-207's 86 bytes that its filer read as tight.
- **AD-038-R31. The OODA knowledge source runs every command inside its own worktree: it never changes into another repository and never runs a package manager (`uv`, `pip`) against one; it reads another repository's files only by reading them.**
  The rule is stated in the session's prompt. The prompt is the only guard: the OODA session runs with the project's
  permission mode, and a guard that refused such a command structurally would be a new hook, which this addendum does
  not build. Whether a stray file in a checkout is dirt is unchanged (c7, AD-038-R1): the defect was the writer, and
  that the dirt was invisible while the queue was empty is SEL-044's to carry.

## 4. What this does not change

Names within the limit file exactly as before; returns' slugs were already cut to 70 characters (`returns.SLUG_MAX`),
so a return is refused only when a consumer's date and token are themselves near the limit. The OODA's verdicts, its
token cap and what it may write are unchanged.
