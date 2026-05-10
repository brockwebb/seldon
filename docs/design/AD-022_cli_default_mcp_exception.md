# AD-022 — CLI-Default, MCP-Exception

**Status:** Proposed, 2026-04-18. Promoted from governing principle in evolution burst 2026-04.
**Supersedes:** None.
**Related:** AD-003 (CLI commands, not MCP servers — original scope was Seldon-only; this AD generalizes).

---

## Context

MCP tool calls burn tokens on every invocation — schema injection, result marshaling, and the round-trip itself. CLI commands invoked via `bash_tool` / `Bash` have structurally lower token cost: the tool surface is loaded once (Claude learns the CLI), and individual invocations are just shell commands with stdout capture.

Empirically, across Seldon/Wintermute/ClaudeClaw operation, most tool use is command-like: run a verify, fetch a node, register an artifact, close a task. These do not require mid-reasoning structured-I/O exchange; they're imperative operations with textual output. For those cases, MCP is strictly worse than CLI — more tokens, more latency, more surface area for tool-schema drift.

MCP's legitimate use case is structured mid-reasoning I/O where the model needs to: (a) inspect structured data, (b) reason over it in the same turn, (c) dispatch a new structured call based on that reasoning, and (d) continue the reasoning trace. Desktop authoring sessions with semantic search are the clearest example: search produces structured results, the model synthesizes across them, and the synthesis feeds back into the next query. In that workflow, CLI + file intermediation breaks the reasoning loop.

## Decision

**Default to CLI invocation via bash for all tool use. MCP is justified only by a specific, identifiable need for structured mid-reasoning I/O.**

The burden of justification is on MCP, not CLI. When designing new tools:
1. Build the CLI first.
2. Add an MCP wrapper only when CLI-via-bash has demonstrated a concrete reasoning-loop problem that MCP solves.

When evaluating existing tools:
1. MCP registrations without active reasoning-loop use cases are candidates for deregistration.
2. Deregistering does not delete the code. The tool remains available as CLI; only the MCP surface is removed. Re-registration is cheap if needed later.

## Consequences

**Positive:**
- Lower per-session token cost on common operations.
- Smaller MCP config surface — fewer registrations to maintain, fewer version drift opportunities.
- Sharper architectural thinking: each MCP registration must justify itself against CLI alternatives.
- New tools ship faster (CLI is cheaper to build and test than MCP).

**Negative / cost:**
- Desktop sessions using CLI via bash lose some structured-output affordances (JSON must be parsed from stdout; no MCP schema validation).
- Mixed-model workflows where one session uses MCP and another uses CLI may have different capabilities for "the same" tool.
- The "reasoning loop" criterion is judgment-based. Borderline cases will require explicit evaluation.

**Reversibility:** High. Deregistering MCP servers does not remove code. A tool that was demoted to CLI-only can be re-promoted to MCP if later use reveals a reasoning-loop need.

## Enforcement

- New tool proposals document (in the proposal) whether they need MCP or just CLI, with reasoning.
- Quarterly review of active MCP registrations: for each, is there an active reasoning-loop use case? If not, deregister.
- CC4 observability dashboard tracks MCP tool call counts; sustained near-zero usage on an MCP registration is a retirement signal.

## Relation to Prior ADs

- **AD-003 (CLI commands, not MCP servers):** Original scope was Seldon-specific. This AD generalizes the principle across Seldon, Wintermute, and any future tool Anthropic's agent ecosystem exposes.
- **AD-023 (Sleep functions):** `wintermute arbitrate` is CLI. AD-022 is the governing principle; AD-023's arbitration CLI is its implementation.

## Open Questions

- Which currently-registered MCP servers clear the "active reasoning-loop use case" bar? Audit deferred to a post-burst cycle.
- Does Claude Code benefit from MCP differently than Desktop? (CC's bash-native workflow may argue for even more aggressive CLI preference.)

---

*Short AD by design. The principle is the contribution; the enforcement is the discipline.*
