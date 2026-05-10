"""`seldon audit-dispatch` — route a single audit prompt through LiteLLM.

Agents shell out to this when AUDIT_MODEL is set so the classification
step runs on a different model family than the orchestrating agent.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from seldon.paper.audit_dispatch import DEFAULT_MODEL, dispatch, resolve_audit_model


@click.command("audit-dispatch")
@click.option("--section", required=True, type=click.Path(exists=True, path_type=Path),
              help="Path to the section file being audited.")
@click.option("--gate", required=True,
              type=click.Choice([
                  "content_audit",
                  "practitioner_stress_test",
                  "argument_completeness",
                  "bloom_depth_check",
                  "secondary_sweep",
              ]),
              help="Which gate's classification prompt to run.")
@click.option("--system-prompt", type=click.Path(exists=True, path_type=Path),
              default=None,
              help="Optional path to a system prompt file. If omitted, a minimal "
                   "gate-specific system prompt is used.")
@click.option("--max-tokens", type=int, default=8192,
              help="Max output tokens from the alt-model call.")
@click.option("--show-model", is_flag=True, default=False,
              help="Print resolved model to stderr before running.")
def audit_dispatch_command(section, gate, system_prompt, max_tokens, show_model):
    """Run one gate's classification prompt on AUDIT_MODEL and print the result.

    Output goes to stdout as raw text (expected to be YAML for most gates).
    Resolved model goes to stderr if --show-model.
    Exit codes:
        0 — dispatch succeeded
        2 — dispatch failed (missing key, bad model string, API error)
    """
    model = resolve_audit_model()
    if show_model:
        label = "claude --print (Max OAuth)" if model == "max" else model
        click.echo(f"audit-dispatch model: {label}", err=True)

    text = section.read_text(encoding="utf-8")
    system = _system_prompt_for(gate, system_prompt)
    user_prompt = _user_prompt_for(gate, section, text)

    try:
        result = dispatch(
            prompt=user_prompt,
            system=system,
            temperature=0.2,
            max_tokens=max_tokens,
        )
    except RuntimeError as exc:
        click.echo(f"audit-dispatch: {exc}", err=True)
        raise SystemExit(2)

    click.echo(result)


def _system_prompt_for(gate: str, override_path: Path | None) -> str:
    """Return system prompt for the requested gate.

    If override_path is provided, read it. Otherwise use a minimal built-in
    that tells the alt model to produce the gate's canonical YAML shape.
    """
    if override_path is not None:
        return override_path.read_text(encoding="utf-8")

    # Minimal built-ins. The agent remains the source of truth for full
    # gate spec; these are fallback prompts for direct CLI use.
    minimal = {
        "content_audit": (
            "You are a content auditor. Classify every substantive assertion "
            "as fact / judgment / conjecture. Check for citation presence on "
            "facts. Output YAML only, no prose preamble. The YAML schema "
            "matches the Seldon auditor.md 'Output Format' section."
        ),
        "practitioner_stress_test": (
            "You are Reviewer 2 at a target academic venue (or a working "
            "practitioner for book chapters). Ask the hardest questions this "
            "section must answer. Output YAML findings only."
        ),
        "argument_completeness": (
            "You are an argument-completeness reviewer for an academic paper. "
            "Check whether each claim is grounded, whether alternative "
            "explanations are addressed, and whether the argument chain has "
            "gaps. Output YAML findings only."
        ),
        "bloom_depth_check": (
            "You are a cognitive-depth reviewer. Assess whether this section "
            "scaffolds a reader to Bloom Evaluate/Create. Output YAML only."
        ),
        "secondary_sweep": (
            "You are a blended-lens reviewer covering narrative arc, clarity/"
            "jargon, visual gaps, and motivational framing. Output YAML only."
        ),
    }
    return minimal[gate]


def _user_prompt_for(gate: str, section: Path, text: str) -> str:
    """Wrap the section text with a minimal gate-specific instruction."""
    return (
        f"File: {section.name}\n"
        f"Gate: {gate}\n"
        f"---\n"
        f"{text}\n"
        f"---\n"
        f"Produce the gate's canonical YAML output. No prose."
    )
