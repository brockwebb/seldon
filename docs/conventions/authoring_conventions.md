# Authoring Conventions — Portable Rules for Seldon-Managed Projects

**Scope:** Rules that apply to any Seldon-managed authoring project (book, paper, report). Project-level CLAUDE.md files add project-specific detail but do not override these.

**Why this document exists:** These rules lived in ai-workflow-design's CLAUDE.md but are general-purpose. The T5 (State Discontinuity) incident on sfv-paper — 11 sections drafted without inline citations — occurred because a new project did not inherit these conventions. They now live here and transfer with `seldon init` or manual project setup.

---

## 1. Citation Conventions

These rules apply to any project with a bibliography.

**Declare the citation format in `seldon.yaml`.** Every project with sources must set `conventions.citation_style` and `conventions.bibliography_path`. A project without this declaration has no citation rules; CC sessions will write bare prose citations by default.

**No bare prose citations.** Do not write "Author et al. (2024)" as plain text. Use the project's citation markup so all build targets (HTML, PDF, etc.) resolve correctly. The exact syntax is project-specific and declared in `seldon.yaml` — for example, MyST projects use `{cite:t}` and `{cite:p}` roles.

**The bibliography file starts at chapter/section 1 and is maintained continuously.** Do not defer bibliography management. Every CC task that introduces a source MUST:
1. Add the bibliography entry to the declared bibliography file.
2. Use the proper citation markup in the text.

Learned from ai4stats: starting the bibliography late creates retroactive cleanup work across every section.

**Citation rules are enforced by the content_audit gate (AD-019).** `citation_gap` findings are routed to `auto_search` — they do not require author judgment. If audit findings are surfacing citation gaps, the underlying cause is usually missing or unenforced conventions in `seldon.yaml`.

---

## 2. CC Task Conventions

**CC tasks are immutable once written to disk.** Corrections go in addendum files, named with the same date prefix and a `_addendum_A` suffix (e.g., `2026-04-03_ch05_review_addendum_A.md`). Never edit a CC task file that has already been executed or registered.

**Naming:**
- CC tasks: `YYYY-MM-DD_<descriptive_slug>.md`
- Addenda: `YYYY-MM-DD_<descriptive_slug>_addendum_A.md`

**CC for execution, Desktop for planning.** CC tasks run in Claude Code (terminal). Desktop sessions (claude.ai, Claude Desktop) plan and create tasks via MCP tools — they do not execute CLI commands. Never attempt to run Seldon CLI from a Desktop session.

**After completing a CC task:** Run `seldon cc complete <task-filepath>` to record completion in the graph. This keeps `seldon go` and `seldon briefing` accurate. Skipping this step causes stale task state to accumulate.

---

## 3. File Operation Conventions

**`str_replace` does not work on the user's filesystem.** Pattern: read full file → modify in memory → write full file back with `Filesystem:write_file`. This applies to all prose edits, bibliography updates, and configuration changes.

**`github:create_or_update_file` is prohibited on Seldon-tracked repos.** This tool is in `conventions.prohibited_tools` in every project's `seldon.yaml`. Use Filesystem MCP for all file writes.

**Symlinks, never copies, for Seldon-managed artifacts.** Agent definitions (auditor.md, cascade-checker.md), templates, and QC scripts are symlinked from the Seldon repo into project directories. Copies drift — confirmed at 363-byte divergence within 24 hours.

---

## 4. Post-Edit Cycle (Paper and Book Projects)

After every section change, run the following in order:

1. **Project-specific QC:** `python paper/check_glossary.py` (or equivalent for the project). Checks terminology, regenerates the keyword index.
2. **Sync to graph:** `seldon paper sync` — computes content hashes, updates `cites` edges, transitions modified sections to `stale`. Without this, the graph doesn't know the edits happened.
3. **Build verify:** `seldon paper build --no-render` — verifies all `{{result:...}}` references still resolve against the graph.

If any step fails, fix before proceeding. Do not commit sections with broken references or glossary violations.

`seldon paper register --all` is the initial setup step — run once to create PaperSection artifacts for all section files. After that, `paper sync` handles updates.

---

## 5. Agent Symlink Setup

Projects that use the audit pipeline must symlink agent definitions from Seldon. Do this before the first audit run.

```bash
mkdir -p .claude/agents
ln -s /Users/brock/Documents/GitHub/seldon/.claude/agents/auditor.md .claude/agents/auditor.md
ln -s /Users/brock/Documents/GitHub/seldon/.claude/agents/cascade-checker.md .claude/agents/cascade-checker.md
```

Verify symlinks are live (not broken):
```bash
ls -la .claude/agents/
```

If the links are broken (Seldon repo moved), recreate them. Never replace with copies.

Agent teams also require this environment setting in Claude Code config:
```json
{ "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" } }
```

---

---

## 6. Register After Stable {#register-after-stable}

Paper section files are registered as `PaperSection` artifacts when the prose
is **structurally stable**, not at drafting time. The graph tracks artifacts
whose content hash is meaningful, not drafts and not perfection.

**Structurally stable** means:

- Addendum-compliance findings are closed
- Tier 2/3 structural findings (long sentences, paragraph shape, section
  closings, missing citations) are resolved
- Citation verification has either completed or has its remaining items
  tracked as blocking `ResearchTask` artifacts

**Does NOT block registration:**

- Style-level findings (inline bold policy, vocabulary repetition, minor
  punctuation preferences)
- One stubborn unresolved citation out of many — track as a blocker task and
  register the section as incomplete-but-known

**Why this rule exists:**

Registering a first-draft would poison the graph with artifacts whose content
hash changes every rewrite pass. Conversely, waiting for "all findings
resolved" means registration never happens because style findings never fully
close. The structural-stability bar splits the difference: register when
the paper *says* what it will say, even if style polishing continues.

**Applies to:** Paper section files specifically. Analogous pattern applies
to other artifact types with drafting-then-stabilizing lifecycles
(DesignNotes, ADs) but the concrete gates differ — see those artifact types'
own conventions.

**Surfaced by:** ICSP paper session, 2026-04-15. Paper drafted in a single CC
pass, registration deferred to post-audit, pattern captured here to prevent
rediscovery on SFV paper.

---

*For pipeline orchestration (gate sequence, run manifest, output naming), see `docs/conventions/audit_pipeline.md`.*
*For project configuration, see `docs/templates/seldon_yaml_template.yaml`.*
