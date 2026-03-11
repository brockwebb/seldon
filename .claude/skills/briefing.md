---
name: briefing
description: Session start protocol. Reads project state, surfaces open tasks, stale results, and next critical path item. Invoke at the beginning of every work session.
---

# Session Briefing

Start every work session by building situational awareness. Do NOT begin implementation until this briefing is complete.

## Procedure

1. **Read the most recent handoff** in `handoffs/` (sort by date, take newest)
   - If no handoffs exist, state that and proceed to step 2

2. **Read the project plan / SRS** to understand overall scope
   - For Seldon: `docs/plans/` and `docs/requirements/`
   - For SAS conversion: `docs/requirements/srs.md` and `docs/proposal.md`
   - For other projects: check `docs/` for planning documents

3. **Scan for open tasks** — search for any task tracking files, TODO markers, or items marked incomplete:
   - Check `handoffs/` for items listed as "next" or "open" or "blocked"
   - Check any `*tasks*` or `*plan*` files for unchecked items `- [ ]`
   - Check `cc_tasks/` for pending task files

4. **Check for stale or unverified results** — look for:
   - Result files or registrations with status != `verified`
   - Test files that haven't been run recently
   - Outputs that may be outdated relative to source changes

5. **Identify the critical path item** — what is the ONE thing that unblocks the most downstream work?

6. **Present the briefing** in this format:

```
## Session Briefing — [Project Name] — [Date]

### Last Session
[Summary from most recent handoff, or "No prior handoffs found"]

### Open Tasks
- [task]: [status] — [what it blocks]
- ...

### Stale/Unverified Results
- [result]: [why it's stale]
- ... (or "None identified")

### Critical Path
[The single most important thing to work on and why]

### Recommended Action
[Specific next step, ready to execute]
```

7. **Wait for confirmation** before beginning implementation. The human may redirect based on the briefing.

## Context Efficiency

- Do NOT read every file in the project. Read handoffs and planning docs only.
- Use `grep` and `find` for targeted searches rather than reading directory trees.
- The briefing should consume minimal context window — save it for the actual work.
