from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from neo4j import Driver

from seldon.core.state import InvalidStateTransition
from seldon.domain.loader import DomainConfig


def propagate_staleness(
    driver: Driver,
    database: str,
    project_dir: Path,
    domain_config: DomainConfig,
    artifact_id: str,
    actor: str = "system",
    session_id: Optional[str] = None,
) -> List[str]:
    """
    Find all downstream artifacts that CITES the given artifact.
    Transition each to 'stale' if the state machine permits it.

    Returns list of affected artifact_ids.

    Called automatically by artifacts.transition_state when new_state == 'stale'.
    Validation is best-effort: artifacts whose state machine does not permit
    a transition to 'stale' are silently skipped.
    """
    # Lazy import to avoid circular dependency (staleness → artifacts → staleness)
    from seldon.core.artifacts import transition_state
    from seldon.core.state import validate_transition

    with driver.session(database=database) as session:
        records = session.run(
            "MATCH (downstream:Artifact)-[:CITES]->(target:Artifact {artifact_id: $id}) "
            "RETURN downstream",
            id=artifact_id,
        ).data()

    affected: List[str] = []

    for r in records:
        downstream: Dict[str, Any] = dict(r["downstream"])
        ds_id = downstream["artifact_id"]
        ds_type = downstream.get("artifact_type", "")
        ds_state = downstream.get("state", "")

        # Skip if this type/state cannot transition to stale
        try:
            validate_transition(domain_config, ds_type, ds_state, "stale")
        except (InvalidStateTransition, ValueError):
            continue

        transition_state(
            project_dir=project_dir,
            driver=driver,
            database=database,
            domain_config=domain_config,
            artifact_id=ds_id,
            artifact_type=ds_type,
            current_state=ds_state,
            new_state="stale",
            actor=actor,
            authority="accepted",
            session_id=session_id,
        )
        affected.append(ds_id)

    return affected


# ---------------------------------------------------------------------------
# Decided, not drifted
# ---------------------------------------------------------------------------
#
# `stale` carries two different facts, and only one of them is a thing to fix.
#
# **Drift** is what the state was built for: something this artifact was derived from moved,
# and nobody has said what that means. It is the warning `seldon verify` exists to raise.
#
# **A decision** is the other one. A withdrawal (`withdrawn_reason`) is a decision, and
# `check_stale_artifacts` has exempted it since ai-readiness-kg's DD-066. A supersession with a
# live successor (`superseded_by`) is the *same kind of fact* and was not exempt: 36 of that
# project's 41 stale artifacts on 2026-09-19 carried a `superseded_by` naming exactly one
# published artifact, and those 36 were the whole of what made `seldon verify` warn and
# `seldon go` print "Stale Artifacts: 41".
#
# Prior art, and the reason this is a status and not a state (read before designing, per the
# operating doctrine): package managers and registries all treat "replaced by" as a terminal,
# NON-ALARMING status, distinct from "broken" — npm `deprecated` with a successor package, PEP
# 592's yanked releases (installable when pinned, invisible to a range), Debian's `Replaces:`.
# None of them invented a new lifecycle state for it; each hangs a pointer to the successor off
# the existing terminal one and teaches the *reporting* to read the pointer. That is exactly
# what this does, and it is why the Result state machine is left alone — the docstring on
# :func:`seldon.commands.verify.check_stale_artifacts` gives the argument in full.
#
# **A pointer that does not resolve is not a decision.** `superseded_by` naming nothing, naming
# two artifacts, or naming an artifact that is itself undecided-stale leaves the artifact in the
# warning set, with the reason on its detail line. Otherwise a typo would silence the check,
# which is the failure mode an exemption has to be designed against.

#: The two bases on which a `stale` artifact is a recorded decision.
BASIS_WITHDRAWN = "withdrawn"
BASIS_SUPERSEDED = "superseded"


@dataclass(frozen=True)
class StaleVerdict:
    """Why one `stale` artifact is, or is not, a decision.

    Attributes:
        decided: True when the artifact records a decision rather than drift.
        basis: ``BASIS_WITHDRAWN``, ``BASIS_SUPERSEDED``, or None when undecided.
        reason: Empty when decided; otherwise the sentence a detail line prints.
    """

    decided: bool
    basis: Optional[str]
    reason: str


#: What a resolver is: a ref (an artifact `name` or an `artifact_id`) to every artifact that
#: matches it, as plain dicts. A function rather than a driver so the predicate is pure and
#: testable against a dict, and so `verify`, `status`, `briefing` and `go` can each hand it the
#: session they already hold.
Resolver = Callable[[str], List[Dict[str, Any]]]


def decided_not_drifted(artifact: Dict[str, Any], resolve: Resolver) -> StaleVerdict:
    """Is this `stale` artifact a recorded decision, or is it drift?

    The ONE predicate every caller that lists or counts stale artifacts uses, so that "Stale
    Artifacts" means the same thing in `seldon verify`, `seldon go`, `seldon briefing` and
    `seldon status`. Four renderers with four filters is how a count starts meaning four things.

    Args:
        artifact: The stale artifact's properties.
        resolve: Maps a `superseded_by` ref to the artifacts it names.

    Returns:
        A :class:`StaleVerdict`. Undecided verdicts carry the reason verbatim, because
        "36 stale" and "36 stale, and here is the one whose successor does not exist" are
        different reports and only the second is actionable.
    """
    return _verdict(artifact, resolve, set())


def _verdict(artifact: Dict[str, Any], resolve: Resolver, visited: set) -> StaleVerdict:
    if str(artifact.get("withdrawn_reason") or "").strip():
        return StaleVerdict(True, BASIS_WITHDRAWN, "")
    ref = str(artifact.get("superseded_by") or "").strip()
    if not ref:
        return StaleVerdict(False, None, "stale with no withdrawal and no superseded_by")
    own = artifact.get("artifact_id")
    if own:
        visited.add(own)
    matches = resolve(ref)
    if not matches:
        return StaleVerdict(False, None, f"superseded_by {ref!r} does not resolve")
    if len(matches) > 1:
        return StaleVerdict(
            False, None,
            f"superseded_by {ref!r} resolves to {len(matches)} artifacts, not one")
    successor = matches[0]
    if str(successor.get("state") or "") != "stale":
        return StaleVerdict(True, BASIS_SUPERSEDED, "")
    # The successor is itself stale, so the question recurses: a supersession chain whose last
    # link is a live artifact is still one decision. A visited set, because a cycle is a
    # pointer that never lands and must not be read as a decision — nor loop the process.
    if successor.get("artifact_id") in visited:
        return StaleVerdict(
            False, None, f"superseded_by {ref!r} closes a supersession cycle")
    inner = _verdict(successor, resolve, visited)
    if inner.decided:
        return StaleVerdict(True, BASIS_SUPERSEDED, "")
    return StaleVerdict(
        False, None, f"superseded_by {ref!r} is itself undecided-stale ({inner.reason})")


@dataclass(frozen=True)
class StalePartition:
    """A stale set split three ways by :func:`decided_not_drifted`.

    Attributes:
        undecided: ``(artifact, reason)`` pairs — the warning set, and the only one.
        withdrawn: Decided by a `withdrawn_reason`.
        superseded: Decided by a `superseded_by` that resolves.
    """

    undecided: List[Tuple[Dict[str, Any], str]]
    withdrawn: List[Dict[str, Any]]
    superseded: List[Dict[str, Any]]

    @property
    def total(self) -> int:
        return len(self.undecided) + len(self.withdrawn) + len(self.superseded)

    @property
    def decided(self) -> int:
        return len(self.withdrawn) + len(self.superseded)

    def undecided_artifacts(self) -> List[Dict[str, Any]]:
        return [a for a, _ in self.undecided]


def partition_stale(artifacts: Iterable[Dict[str, Any]], resolve: Resolver) -> StalePartition:
    """Split every `stale` artifact into undecided, withdrawn and superseded."""
    undecided: List[Tuple[Dict[str, Any], str]] = []
    withdrawn: List[Dict[str, Any]] = []
    superseded: List[Dict[str, Any]] = []
    for artifact in artifacts:
        verdict = decided_not_drifted(artifact, resolve)
        if not verdict.decided:
            undecided.append((artifact, verdict.reason))
        elif verdict.basis == BASIS_WITHDRAWN:
            withdrawn.append(artifact)
        else:
            superseded.append(artifact)
    return StalePartition(undecided=undecided, withdrawn=withdrawn, superseded=superseded)


def resolver_for_session(session) -> Resolver:
    """A :data:`Resolver` over one Neo4j session.

    Matches on `name` OR `artifact_id`, because `superseded_by` is written by hand and both
    spellings are in the field: ai-readiness-kg writes the successor's NAME
    (`scan_findings_2026-09-10_rj2` names `scan_findings_2026-09-10_rj4`), while
    `seldon task supersede` records an id.
    """
    cache: Dict[str, List[Dict[str, Any]]] = {}

    def resolve(ref: str) -> List[Dict[str, Any]]:
        if ref not in cache:
            rows = session.run(
                "MATCH (a:Artifact) WHERE a.name = $ref OR a.artifact_id = $ref RETURN a",
                ref=ref,
            ).data()
            cache[ref] = [dict(r["a"]) for r in rows]
        return cache[ref]

    return resolve


def stale_label(artifact: Dict[str, Any]) -> str:
    """What to call an artifact on a one-line report: its name, else a short id."""
    return str(artifact.get("name") or str(artifact.get("artifact_id") or "?")[:8])
