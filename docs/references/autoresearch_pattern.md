# The Autoresearch Pattern

**Source:** [karpathy/autoresearch](https://github.com/karpathy/autoresearch) (March 2026, MIT)
**macOS fork:** [miolini/autoresearch-macos](https://github.com/miolini/autoresearch-macos) (runs on M1 Pro)

## What It Is

An autonomous experiment loop where an AI agent (Claude Code, Codex, etc.) iteratively modifies code, runs fixed-budget experiments, evaluates results against a single metric, and keeps or discards changes — all without human intervention. The human sleeps; the agent runs ~100 experiments overnight.

## Why It Matters for Seldon

This is the minimum viable version of Seldon's experiment-and-result tracking loop, stripped to essentials. It validates the core pattern while making clear exactly why Seldon needs more infrastructure for multi-artifact, multi-metric, multi-session research workflows.

### Direct Mappings

| autoresearch | Seldon equivalent |
|---|---|
| `results.tsv` (tab-separated log) | Result Registry (AD-006) |
| git commit = checkpoint | Event-sourced JSONL append-only log |
| keep/discard status column | State machine: proposed → verified → published |
| `program.md` = agent instructions | Session briefing via `seldon briefing` |
| git branch = experiment state | Per-project graph database |
| `grep run.log` for metrics | `seldon result register` |
| `git reset` on failure | Soft delete via event sourcing |
| TSV = the briefing | `seldon briefing` surfaces open tasks, stale results |

### Key Design Decisions Worth Adopting

1. **Fixed budget per experiment.** 5 minutes wall clock regardless of what changes. Makes all experiments directly comparable. Apply this whenever running automated analysis sweeps.

2. **Single metric as keep/discard gate.** val_bpb — lower is better. No ambiguity in the authority model. For Seldon: define primary metrics per research task upfront.

3. **`program.md` as lightweight agent skill.** The entire autonomous research protocol is a single markdown file the agent reads. This is what CC task files and CLAUDE.md should aspire to: complete, self-contained instructions that an agent can follow without interruption.

4. **Git as state machine.** Branch = experiment state. Commit = checkpoint. Reset = discard. No external infrastructure needed for the authority model. For simpler Seldon use cases, git-based state tracking may be sufficient before the full event-sourced engine exists.

5. **"NEVER STOP" instruction.** The agent runs indefinitely until manually interrupted. Critical for overnight/unattended autonomous operation. Explicit instruction not to pause for confirmation.

6. **Simplicity criterion.** "All else being equal, simpler is better. A small improvement that adds ugly complexity is not worth it. Removing something and getting equal or better results is a great outcome." This should be in every CC task file.

## Where autoresearch Falls Short (Why Seldon Exists)

- **Single file, single metric.** Real research has cross-artifact dependencies, multiple metrics, and provenance chains.
- **No provenance.** Can't trace from a result back through the data/script/requirement chain.
- **No task tracking.** No way to formalize sub-tasks, track completion, or surface blocking dependencies.
- **No session continuity.** Each agent invocation is independent. No briefing, no closeout, no accumulated context.
- **TSV doesn't scale.** Flat log works for 100 experiments on one file. Breaks with 481 artifacts across a research project.
- **No cross-experiment connections.** Each experiment is evaluated in isolation. No graph of how experiments relate to each other.

## How to Use This Pattern

### For CC Task Files

Adopt the `program.md` structure when writing CC task files for autonomous work:
- Clear scope (what to modify, what not to touch)
- Single success metric
- Explicit keep/discard decision rule
- Logging format and location
- "Don't stop" instruction for unattended operation
- Crash recovery protocol

### For Quick Experiment Sweeps

Clone [miolini/autoresearch-macos](https://github.com/miolini/autoresearch-macos) for M1 Pro. Point Claude Code at `program.md`. Let it iterate on `train.py` overnight. Review `results.tsv` in the morning.

### For Seldon Session Protocol Design

When implementing `seldon briefing` and `seldon closeout` (T2-5, T2-6 in the project plan), reference this pattern for the minimal viable loop: read state → modify → execute → evaluate → keep/discard → log → repeat.
