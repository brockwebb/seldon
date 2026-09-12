# RESULT: `seldon handoff` Desktop closeout tool

**Date:** 2026-09-12
**Task file:** `cc_tasks/2026-09-12_seldon_handoff_tool.md`
**Seldon task:** a5c372d1
**Governing doc:** `docs/design/AD-030_governed_documents_as_graph_content.md`, ruling AD-030-R9
**Addenda read:** none exist. `find . -iname "*ADDENDUM*"` over the repo returned nothing.

---

## 1. What shipped

| Deliverable | Location |
|---|---|
| Session window, R9 gate, document generation | `seldon/core/handoff.py` (new) |
| CLI surface | `seldon/commands/handoff.py` (new), registered in `seldon/cli.py` |
| MCP parity | `seldon_handoff` in `seldon/mcp_server.py` |
| Desktop contract line + previous-session R9 report | `seldon/commands/go.py` |
| Config keys | `seldon.yaml` (this repo) and `seldon/commands/init.py` (new projects) |
| Tests | `tests/test_handoff.py` — 32 tests |

**Suite:** 1574 passed (was 1542 at start; +32 new). `seldon verify --strict` exit 0.

## 2. Success contract, verified

- `seldon handoff --slug x --summary y --next z` writes `handoffs/<date>_<slug>.md` and prints
  both blocks. Verified on this repo with `--dry-run`; the CC dispatch block correctly reported
  `No CC task ready — no CC task file was registered in this session window`, and Open tasks
  rendered `d7fb603f` without the `▸` marker because `343cb6fe precedes d7fb603f` (AD-029).
- Refuses when a Desktop task exists in the window and no `docs/design/` file changed
  (`test_cli_refuses_an_r9_violation`, `test_r9_refuses_desktop_tasks_without_a_design_note`).
- Warns instead when `handoff.require_design_note: false`
  (`test_r9_warns_instead_of_refusing_when_configured`).

## 3. Decisions taken during implementation

**D1. The session window's handoff boundary trusts the declared date over mtime.**
Step 1 says "the newest ... handoff file" without saying which timestamp that means. Modification
time is destroyed by a fresh clone — every file gets the checkout time, which would put the window
start at "now" and make every generated handoff silently blank. The filename's `YYYY-MM-DD` prefix
is the authoritative session marker under the convention `seldon/commands/go.py` already
implements. `handoff_boundary()` therefore uses mtime **only when it falls on the declared date**,
which keeps a second same-day session bounding precisely, and falls back to the declared date
otherwise. A marker that lands in the future (clock skew, a handoff dated ahead) falls through to
the configured window rather than producing an empty report.

**D2. `seldon go` gained an optional handoff-path argument.**
Step 4 fixes the resume block's first line as `seldon go --brief <absolute handoff path>`. That
form did not parse: `--brief` is a flag and `go` took no argument, so the command every resume
block emits — including the one the 2026-09-12 Desktop session hand-wrote — would have exited with
"Got unexpected extra argument". `go_command` now takes an optional `HANDOFF_PATH`; when given,
that file is read as the Latest Handoff section instead of auto-discovering the newest. A path
that does not exist is an error, not a silent fall-through to the newest file, because silently
orienting on the wrong session is worse than failing. Covered by `test_go_opens_on_the_named_handoff`
and `test_go_reports_a_missing_named_handoff`. No change to the emitted text.

**D3. Config defaults live as named module constants, and are written at `seldon init`.**
"Never hardcode" (standards §2) is satisfied by `handoff.session_window_hours` and
`handoff.require_design_note` in `seldon.yaml`, which `seldon init` now writes for every new
project. `DEFAULT_SESSION_WINDOW_HOURS = 12` and `DEFAULT_REQUIRE_DESIGN_NOTE = True` exist as
named, documented constants for projects whose config predates this command; they are never
consulted when the key is present. A present-but-unusable value (non-numeric, zero, negative) is
refused with `ValueError` rather than coerced, because a silently truncated window produces a
report that looks complete and is not.

**D4. Empty CC dispatch distinguishes two cases.** "No CC task ready" alone cannot be acted on.
The block names which of the two held: nothing was registered in the window, or everything
registered has already left `proposed`.

**D5. An existing handoff at the same path is not overwritten.** Standards §11 forbids replacing a
file with a "new version". A handoff is the record of a session that happened; `--force` is the
explicit override.

## 4. Findings against AD-030

**F1. AD-030-R9's trigger is under-specified for non-Desktop actors, and the implementation reads
it narrowly.** R9 says "A Desktop design session closes with a design note". The gate here fires
only on `created_by = desktop` ResearchTasks, per this task's step 2. A CC session that files tasks
is unaffected — correctly, since CC executes decisions rather than making them — but the ruling
does not say so, and a future actor string (an autonomous agent, say) would silently escape the
gate. Not fixed here; AD-030 is not to be edited by this task.

**F2. The filesystem-mtime form of the R9 check cannot see a design note that was written, then
committed and checked out elsewhere.** This is the transitional form the task specifies
("the DesignNote node check is added when AD-030 ingest lands"). Step C7 of
`cc_tasks/2026-09-12_ad030_governed_docs_ingest.md` replaces it.

## 5. Scope boundaries observed

- No second term for closeout introduced. `seldon closeout` (lab-notebook entry, unchanged) and
  `seldon handoff` (Desktop session close) are distinct commands with distinct jobs; the Desktop
  contract in `seldon go` names only `handoff`.
- `docs/design/AD-030_*.md` not edited.
- The DesignNote-node form of the R9 check not implemented.
