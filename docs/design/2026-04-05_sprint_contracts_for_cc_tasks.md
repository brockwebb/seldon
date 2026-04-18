# Design Note: Sprint Contracts for CC Task Execution

**Date:** 2026-04-05
**Status:** Design
**Relates to:** AD-021 (Session Continuity Fidelity), AD-020 (Iterative Content Review Pipeline)
**Provenance:** Pattern extracted from Anthropic's harness engineering research (Rajasekaran, March 2026). Their three-agent architecture uses generator-evaluator contract negotiation before each sprint. Pattern adapted for Seldon's CC task execution model.
**note_type:** pattern_proposal

---

## 1. Context

CC tasks currently define what to do (specification) and what success looks like (success criteria). The executing agent reads the task, does the work, and reports completion. There is no structured step where the executing agent proposes its verification plan and gets that plan reviewed before starting.

This gap is invisible on simple tasks (bug fixes, schema changes) but surfaces on complex multi-part tasks where the specification is necessarily high-level. The semantic anchoring CC task (`149d34d4`) is a representative example: schema changes, a new relationship type, a new CLI command, tests, and documentation updates — all in one task. The specification was detailed, but the executing agent still had to make judgment calls about how to verify each part. Those verification decisions were unreviewed.

## 2. The Pattern: Pre-Execution Success Contracts

Before executing a complex CC task, the executing agent produces a **success contract** — a structured document listing:

1. **Deliverables**: What artifacts will be created or modified (files, graph nodes, edges)
2. **Verification steps**: How each deliverable will be tested (specific commands, expected output)
3. **Acceptance thresholds**: What constitutes pass/fail for each verification step
4. **Scope boundaries**: What the task explicitly does NOT do (prevents scope creep)

The contract is written to a file (e.g., `cc_tasks/<task_name>_contract.md`) and reviewed before execution proceeds. Review can be:

- **Human review**: Author reads the contract and approves (current workflow — Desktop session reviews CC output)
- **Evaluator agent review**: A separate agent reviews the contract against the original specification (future — requires agent role definition)
- **Self-review with structured checklist**: The executing agent reviews its own contract against a checklist template (lightweight — can implement immediately)

### What This Prevents

1. **Specification gaps surfaced late**: The agent discovers mid-execution that the task didn't specify how to handle an edge case. With a contract, this surfaces during planning.
2. **Verification drift**: The agent marks work complete based on "it compiled" rather than "the specific behavior described in the spec works end-to-end."
3. **Scope creep**: Without explicit boundaries, the agent may implement adjacent features not in the spec, consuming tokens and potentially introducing bugs.
4. **Unstated assumptions**: The contract forces the agent to state what it assumes about the codebase before touching it.

### When to Use

Not every CC task needs a contract. The trigger should be complexity, not ceremony:

- **No contract needed**: Single-function bug fixes, schema-only changes, documentation updates, file registration tasks
- **Contract recommended**: Tasks with 3+ parts, tasks that modify both schema and code, tasks that require new test files, tasks where the specification says "check whether X exists and handle accordingly"

### Template

```markdown
# Success Contract: <task name>

## Deliverables
1. <file or artifact> — <what changes>
2. ...

## Verification Plan
| Deliverable | Verification Command | Expected Result |
|-------------|---------------------|-----------------|
| ... | ... | ... |

## Scope Boundaries
- This task does NOT: ...
- Assumptions: ...

## Pre-execution Checklist
- [ ] Read the full CC task specification
- [ ] Checked current state of all files to be modified
- [ ] Identified dependencies (other tasks, schema state, test fixtures)
- [ ] Contract reviewed and approved
```

## 3. Integration with Seldon

**Immediate (template-level):** Add a `## Success Contract` section to the CC task template in `docs/templates/`. Complex tasks include it; simple tasks omit it. No tooling changes required.

**Near-term (CC task workflow):** Modify CC task template guidance in CLAUDE.md to recommend contracts for multi-part tasks. Add contract file convention: `cc_tasks/<date>_<name>_contract.md`.

**Future (evaluator agent):** Define an `Evaluator` agent role (AD-014 extension) whose retrieval profile includes the CC task spec and whose job is to review the contract for completeness. This is the Anthropic pattern — separated evaluation. Deferred until the manual contract pattern has been dogfooded.

## 4. Relationship to Existing Patterns

- **AD-020 gates**: Gates evaluate finished output. Contracts evaluate the plan before execution starts. Complementary, not overlapping.
- **AD-021 CC task tracking**: Contracts don't change the state machine. A task with a contract still goes through proposed → accepted → in_progress → completed. The contract is an artifact of the planning phase within `in_progress`.
- **Semantic anchoring**: The `paper context` command provides retrieval context for revision tasks. Contracts provide execution context for implementation tasks. Same principle (structured context before work), different domain.

## 5. Open Questions

1. **Contract storage**: Should contracts be separate files or inline sections in the CC task? Separate files maintain CC task immutability. Inline sections are simpler to track.
2. **Contract review latency**: If the author must review every contract before execution, this adds a synchronous bottleneck to the CC workflow. Is self-review with a checklist sufficient for most cases?
3. **Evaluator agent scope**: When the evaluator role is defined, should it also review CC task output (post-execution), or only contracts (pre-execution)? Anthropic does both — the evaluator grades each sprint's output.

## 6. Recommendation

Implement at the template level first. Add the contract template to `docs/templates/`. Update CLAUDE.md guidance. Dogfood on the next complex CC task. Observe whether contracts catch specification gaps that would have surfaced mid-execution. Decide on evaluator agent role after 3-5 contract cycles provide data.

---

*This design note will be registered as a DesignNote artifact with `informs` edges to AD-021 and AD-020.*
