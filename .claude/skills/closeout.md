---
name: closeout
description: Session end protocol. Captures what was accomplished, registers results, updates task status, writes structured handoff. Invoke at the end of every work session.
---

# Session Closeout

End every work session by capturing state. The next session (possibly weeks later, possibly a different Claude instance) must be able to resume without the human re-explaining context.

## Procedure

1. **Inventory what changed this session**
   - Run `git diff --stat` to see modified files
   - Run `git log --oneline -10` to see recent commits
   - If uncommitted changes exist, note them explicitly

2. **Capture results** — for any quantitative output produced this session:
   - What was the result (value, meaning)?
   - What script/command produced it?
   - What input data was used?
   - Is it verified (tests pass, trace matches) or provisional?
   - Write to `output/results/` as structured YAML if a results directory exists, otherwise note in the handoff

3. **Update task status** — for any tasks worked on:
   - Mark completed items in any task tracking files (`- [x]`)
   - Note partially completed items with current state
   - Note newly discovered tasks or blockers

4. **Write the handoff** to `handoffs/YYYY-MM-DD_<slug>.md`:

```markdown
# Handoff — [Date] — [Slug]

## Accomplished
- [Concrete thing done, with file paths]
- [Another thing, with evidence of completion]

## Results Registered
- [Result name]: [value] — [status: provisional|verified] — [source: script/command]
- ... (or "None this session")

## Decisions Made
- [Decision]: [Rationale]
- ... (or "None")

## Open Items
- [ ] [Task]: [Current state, what's needed to complete]
- [ ] [Task]: [Blocked by X]

## Next Session Should
1. [Most important thing to do first]
2. [Second priority]
3. [If time permits]

## Files Modified
[git diff --stat output or manual list]
```

5. **Commit the handoff** — `git add handoffs/ && git commit -m "handoff: YYYY-MM-DD session closeout"`

## Rules

- Handoffs are written for someone with ZERO context about this session.
- Include absolute file paths, not relative descriptions.
- "I worked on the parser" is useless. "Implemented FR-001 through FR-003 in `src/extractor/data_step_parser.py`, tests passing in `tests/test_data_step.py`" is useful.
- If you didn't finish something, say exactly where you stopped and what the next concrete step is.
- NEVER skip the handoff. Even if "nothing happened," write a handoff explaining why.
