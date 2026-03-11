---
name: task-track
description: Create and manage research tasks with state machines. Use when work items need to be tracked across sessions — things that block other work, things that must not be forgotten.
---

# Task Tracking

Research tasks are things that must happen but might not happen THIS session. They cross session boundaries. Without tracking, they fall through the cracks — this is the exact failure mode Seldon exists to prevent.

## When to Create a Task

- A computation needs to be re-run but not right now
- A result needs verification before it can be cited
- A dependency must be resolved before downstream work can proceed
- Something was discovered that needs investigation later
- A reviewer or collaborator needs to do something
- You notice an error or gap that can't be fixed this session

## Task File Format

Create in the project's task tracking location. Check for an existing `tasks/` directory or `cc_tasks/` first. If neither exists, create `tasks/`.

Filename: `YYYY-MM-DD_<descriptive-slug>.md`

```markdown
# Task: [Short descriptive title]

**ID:** task-YYYYMMDD-<short_slug>
**Created:** YYYY-MM-DD
**Status:** proposed  <!-- proposed | accepted | in_progress | completed | verified | dropped -->
**Priority:** [critical | high | medium | low]
**Blocks:** [What can't proceed until this is done — be specific]
**Depends On:** [What must be done before this can start]

## Description

[Clear, actionable description. Someone with zero context should be able to do this.]

## Acceptance Criteria

- [ ] [Specific, testable condition that means this task is done]
- [ ] [Another condition]

## Evidence of Completion

[What artifact proves this was done? A test passing? A file existing? A result registered?]

## Notes

[Context, rationale, related decisions. Why does this task exist?]

## History

- YYYY-MM-DD: Created — [reason]
- YYYY-MM-DD: Status → [new status] — [reason]
```

## State Machine

```
proposed → accepted → in_progress → completed → verified
                                  ↘ dropped (with reason)
```

- **proposed**: Someone thinks this needs doing. Not yet committed.
- **accepted**: Committed to doing this. On the plan.
- **in_progress**: Actively being worked on.
- **completed**: Done, but not yet verified.
- **verified**: Completion evidence confirmed. Terminal state.
- **dropped**: Decided not to do this. MUST include reason. Terminal state.

## Rules

- Tasks that block downstream work are ALWAYS priority `critical` or `high`.
- When completing a task, update the status AND record evidence in the History section.
- When the briefing skill surfaces a task, check if it's still relevant before working on it.
- NEVER delete a task file. Change status to `dropped` with a reason instead.
- Link tasks to results: if a task produces a number, register it with `result-register` and reference the result ID in the task's evidence.

## Discovery

To find open tasks across a project:
```bash
grep -rl "Status: proposed\|Status: accepted\|Status: in_progress" tasks/ cc_tasks/ 2>/dev/null
```

To find what's blocked:
```bash
grep -l "Priority: critical\|Priority: high" tasks/ cc_tasks/ 2>/dev/null | xargs grep "Blocks:"
```
