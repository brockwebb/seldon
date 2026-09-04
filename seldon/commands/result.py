"""
`seldon result` CLI group — register, verify, trace, and migrate Result artifacts.

AD-028 split two meanings that used to share the `units` property: `name` is the
stable token key that `{{result:NAME:field}}` resolves against, and `units` is a
real unit of measurement. See docs/conventions/result_units_vocabulary.md.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import click
import yaml

from seldon.config import load_project_config, get_neo4j_driver, get_current_session
from seldon.core.artifacts import create_artifact, create_link, transition_state, update_artifact
from seldon.core.graph import get_artifact, get_artifacts_by_type, get_artifacts_by_state, get_provenance_chain, get_stale_artifacts, get_dependents, find_artifact_by_property
from seldon.domain.loader import load_domain_config
from seldon.domain.units_vocabulary import load_units_vocabulary
from seldon.paper.build import REFERENCE_PATTERN

# The AD-028 name grammar lives in `seldon.core.naming`, a leaf module that
# imports nothing from Seldon. It cannot live here: this module imports
# REFERENCE_PATTERN from `seldon.paper.build`, and `build` must embed the name
# grammar in that pattern, so defining it here makes the pair circular. These
# re-exports keep `seldon.commands.result.RESULT_NAME_PATTERN` working for
# existing callers.
from seldon.core.naming import (  # noqa: F401  (re-exported for callers)
    RESULT_NAME_GRAMMAR_PROSE,
    RESULT_NAME_MAX_LENGTH,
    RESULT_NAME_PATTERN,
)

#: Classification buckets emitted by `seldon result migrate-names`, in report
#: order. Every Result in the graph lands in exactly one, so the summary table
#: reconciles against the total row count.
#:
#: - ``migrated``               units is promoted to name and units cleared
#: - ``name_set_units_pending`` name already set, units still holds the same
#:                              string (a half-applied earlier migration) —
#:                              clear units only
#: - ``already_named``          name set and units is a real unit or absent —
#:                              nothing to do; this is what makes the command
#:                              resumable
#: - ``units_is_real_unit``     no name, units is a genuine unit — leave alone
#: - ``ambiguous``              no name, cannot be assigned without a human
#: - ``no_units``               no name and no units — nothing is inferable
#: - ``refused``                would be migrated, but the resulting name fails
#:                              the validation the live path applies
MIGRATION_CLASSES = (
    "migrated",
    "name_set_units_pending",
    "already_named",
    "units_is_real_unit",
    "ambiguous",
    "no_units",
    "refused",
)

#: Classes whose rows the live run writes an event for.
MIGRATION_WRITING_CLASSES = ("migrated", "name_set_units_pending")

#: Field order of the `--report PATH` JSONL. This is a consumed contract —
#: `ai-readiness-kg/cc_tasks/2026-09-04_result_migration_completion.md` reads it.
#: Adding a field is safe; renaming or removing one is a breaking change.
MIGRATION_REPORT_FIELDS = (
    "artifact_id",
    "current_name",
    "current_units",
    "class",
    "planned_action",
    "reason",
)

#: How many rows of each class the migration report prints before summarising.
#: `ambiguous` and `refused` are always listed in full — those are the classes a
#: human has to adjudicate, and truncating them is how a refusal goes unnoticed.
#: `--show-all` lifts the cap; `--report PATH` writes every row regardless.
MIGRATION_REPORT_PREVIEW = 20


def _get_domain_config(config: dict):
    domain_name = config["project"].get("domain", "research")
    domain_yaml = Path(__file__).parent.parent / "domain" / f"{domain_name}.yaml"
    return load_domain_config(domain_yaml)


def validate_result_name(name: str) -> None:
    """Validate a Result `name` against the AD-028 slug grammar.

    Args:
        name: The candidate token key.

    Returns:
        None if the name is valid.

    Raises:
        ValueError: If the name is empty, longer than
            RESULT_NAME_MAX_LENGTH characters, or does not match
            RESULT_NAME_PATTERN (the single definition point for the grammar —
            see the constant, which is deliberately not restated here). The
            message names the offending value and the grammar it violated.
    """
    if not name:
        raise ValueError("Result --name is required and must not be empty")
    if len(name) > RESULT_NAME_MAX_LENGTH:
        raise ValueError(
            f"Result name '{name[:40]}...' is {len(name)} characters; "
            f"the limit is {RESULT_NAME_MAX_LENGTH}"
        )
    if not RESULT_NAME_PATTERN.match(name):
        raise ValueError(
            f"Result name '{name}' does not match the required slug grammar "
            f"{RESULT_NAME_PATTERN.pattern} — it {RESULT_NAME_GRAMMAR_PROSE}. "
            f"Names are case-sensitive (AD-028 §1 as amended by Amendment 01)."
        )


def find_result_by_name(session, name: str) -> Optional[dict]:
    """Return the Result node carrying this `name`, or None.

    Args:
        session: Active Neo4j session bound to the project database.
        name: Exact, case-sensitive name to look up.

    Returns:
        The Result node as a dict, or None when no Result carries the name. If
        the graph already holds more than one (a pre-AD-028 graph could), the
        oldest by creation is returned so the collision message is stable.

    Raises:
        Nothing.
    """
    records = session.run(
        "MATCH (r:Result) WHERE r.name = $name "
        "RETURN r ORDER BY r.created_at ASC",
        name=name,
    ).data()
    if not records:
        return None
    return dict(records[0]["r"])


@click.group("result")
def result_group():
    """Manage Result artifacts — register, verify, trace provenance."""
    pass


@result_group.command("register")
@click.option("--name", "name", required=True,
              help="Stable token key for {{result:NAME:field}} references. "
                   f"Slug {RESULT_NAME_PATTERN.pattern}, case-sensitive, "
                   f"<={RESULT_NAME_MAX_LENGTH} chars, unique per project "
                   "graph (AD-028).")
@click.option("--value", required=True, type=float, help="Numeric result value")
@click.option("--units", default="", help="Units of measurement (e.g. 'accuracy', 'ms'). "
                                          "A real unit only — never a token key; use --name for that.")
@click.option("--description", default="", help="Human-readable description")
@click.option("--script-id", default=None, help="UUID of Script that generated this result")
@click.option("--data-ids", default=None, help="Comma-separated UUIDs of DataFile inputs")
@click.option("--script-name", default=None, help="Name of Script artifact (resolved by 'name' property)")
@click.option("--script-path", default=None, help="Path of Script artifact (resolved by 'path' property)")
@click.option("--data-name", default=None, help="Comma-separated names of DataFile artifacts")
@click.option("--requirement-id", default=None, help="UUID of SRS_Requirement this implements")
@click.option("--input-hash", default=None, help="SHA256 hash of input data")
def result_register(name, value, units, description, script_id, data_ids, script_name, script_path, data_name, requirement_id, input_hash):
    """Register a new Result artifact with optional provenance links.

    Every reference supplied on the command line is resolved and validated
    BEFORE any event is written. An unknown Script or DataFile, a malformed
    --name, or a name already taken in this graph aborts with exit code 1 and
    an empty event log (AD-028): a Result whose provenance link was silently
    dropped is worse than no Result at all.
    """
    config = load_project_config()
    project_dir = Path.cwd()
    driver = get_neo4j_driver(config)
    domain_config = _get_domain_config(config)
    database = config["neo4j"]["database"]
    session_id = get_current_session(project_dir)

    def _abort(message: str) -> None:
        """Print an error, close the driver, and exit non-zero without writing."""
        click.echo(f"Error: {message}", err=True)
        driver.close()
        raise SystemExit(1)

    # ── AD-028: name grammar, checked before anything touches the graph ──
    try:
        validate_result_name(name)
    except ValueError as e:
        _abort(str(e))

    # ── AD-028: name uniqueness within this project graph ──
    with driver.session(database=database) as sess:
        existing = find_result_by_name(sess, name)
    if existing is not None:
        _abort(
            f"A Result named '{name}' already exists in database '{database}': "
            f"artifact_id {existing.get('artifact_id')} "
            f"(value={existing.get('value')}, state={existing.get('state')}). "
            f"Result names are unique per project graph. Choose another --name."
        )

    # ── Resolve every reference up front; collect ALL failures, then abort ──
    unresolved: list[str] = []

    # Script: --script-id takes priority, then --script-name, then --script-path
    resolved_script_id = None
    if script_id:
        with driver.session(database=database) as sess:
            node = get_artifact(sess, script_id)
        if node is None:
            unresolved.append(f"--script-id '{script_id}': no artifact with that id")
        else:
            resolved_script_id = node["artifact_id"]

    if resolved_script_id is None and script_name:
        with driver.session(database=database) as sess:
            node = find_artifact_by_property(sess, "Script", "name", script_name)
        if node is None:
            unresolved.append(f"--script-name '{script_name}': no Script with that name")
        else:
            resolved_script_id = node["artifact_id"]

    if resolved_script_id is None and script_path:
        with driver.session(database=database) as sess:
            node = find_artifact_by_property(sess, "Script", "path", script_path)
        if node is None:
            unresolved.append(f"--script-path '{script_path}': no Script with that path")
        else:
            resolved_script_id = node["artifact_id"]

    # DataFiles supplied by id
    resolved_data_ids: list[str] = []
    if data_ids:
        for did in data_ids.split(","):
            did = did.strip()
            if not did:
                continue
            with driver.session(database=database) as sess:
                node = get_artifact(sess, did)
            if node is None:
                unresolved.append(f"--data-ids '{did}': no artifact with that id")
            else:
                resolved_data_ids.append(node["artifact_id"])

    # DataFiles supplied by name
    resolved_data_names: list[str] = []
    if data_name:
        for dname in data_name.split(","):
            dname = dname.strip()
            if not dname:
                continue
            with driver.session(database=database) as sess:
                node = find_artifact_by_property(sess, "DataFile", "name", dname)
            if node is None:
                unresolved.append(f"--data-name '{dname}': no DataFile with that name")
            else:
                resolved_data_names.append(node["artifact_id"])

    # Requirement supplied by id
    resolved_requirement_id = None
    if requirement_id:
        with driver.session(database=database) as sess:
            node = get_artifact(sess, requirement_id)
        if node is None:
            unresolved.append(f"--requirement-id '{requirement_id}': no artifact with that id")
        else:
            resolved_requirement_id = node["artifact_id"]

    if unresolved:
        for problem in unresolved:
            click.echo(f"Error: {problem}", err=True)
        click.echo(
            "No Result was registered and no event was written. "
            "Register the missing artifacts first, or drop the flag.",
            err=True,
        )
        driver.close()
        raise SystemExit(1)

    props = {
        "name": name,
        "value": value,
        "run_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if units:
        props["units"] = units
    if description:
        props["description"] = description
    if input_hash:
        props["input_data_hash"] = input_hash

    try:
        result_id = create_artifact(
            project_dir=project_dir, driver=driver, database=database,
            domain_config=domain_config, artifact_type="Result",
            properties=props, actor="human", authority="accepted",
            session_id=session_id,
        )

        links_created = []

        if resolved_script_id:
            create_link(
                project_dir=project_dir, driver=driver, database=database,
                domain_config=domain_config,
                from_id=result_id, to_id=resolved_script_id,
                from_type="Result", to_type="Script",
                rel_type="generated_by", actor="human", authority="accepted",
                session_id=session_id,
            )
            links_created.append(f"GENERATED_BY {resolved_script_id[:8]}...")

        for data_id in resolved_data_ids:
            create_link(
                project_dir=project_dir, driver=driver, database=database,
                domain_config=domain_config,
                from_id=result_id, to_id=data_id,
                from_type="Result", to_type="DataFile",
                rel_type="computed_from", actor="human", authority="accepted",
                session_id=session_id,
            )
            links_created.append(f"COMPUTED_FROM {data_id[:8]}...")

        for data_id in resolved_data_names:
            create_link(
                project_dir=project_dir, driver=driver, database=database,
                domain_config=domain_config,
                from_id=result_id, to_id=data_id,
                from_type="Result", to_type="DataFile",
                rel_type="computed_from", actor="human", authority="accepted",
                session_id=session_id,
            )
            links_created.append(f"COMPUTED_FROM {data_id[:8]}... (by name)")

        if resolved_requirement_id:
            create_link(
                project_dir=project_dir, driver=driver, database=database,
                domain_config=domain_config,
                from_id=result_id, to_id=resolved_requirement_id,
                from_type="Result", to_type="SRS_Requirement",
                rel_type="implements", actor="human", authority="accepted",
                session_id=session_id,
            )
            links_created.append(f"IMPLEMENTS {resolved_requirement_id[:8]}...")

        click.echo(f"Registered Result: {result_id}")
        click.echo(f"  name: {name}")
        click.echo(f"  value: {value} {units}")
        click.echo(f"  state: proposed")
        if links_created:
            click.echo(f"  links: {', '.join(links_created)}")

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
    finally:
        driver.close()


@result_group.command("verify")
@click.argument("result_id")
def result_verify(result_id):
    """Mark a Result as verified (proposed → verified)."""
    config = load_project_config()
    project_dir = Path.cwd()
    driver = get_neo4j_driver(config)
    domain_config = _get_domain_config(config)
    database = config["neo4j"]["database"]
    session_id = get_current_session(project_dir)

    with driver.session(database=database) as session:
        node = get_artifact(session, result_id)

    if node is None:
        click.echo(f"Error: Result '{result_id}' not found", err=True)
        driver.close()
        raise SystemExit(1)

    try:
        transition_state(
            project_dir=project_dir, driver=driver, database=database,
            domain_config=domain_config, artifact_id=result_id,
            artifact_type="Result", current_state=node["state"], new_state="verified",
            actor="human", authority="accepted",
            session_id=session_id,
        )
        value = node.get("value", "?")
        units = node.get("units", "")
        click.echo(f"Verified Result: {result_id}")
        click.echo(f"  value: {value} {units}")
        click.echo(f"  state: {node['state']} → verified")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
    finally:
        driver.close()


@result_group.command("list")
@click.option("--state", default=None, help="Filter by state (proposed/verified/published/stale)")
def result_list(state):
    """List Result artifacts."""
    config = load_project_config()
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]

    with driver.session(database=database) as session:
        if state:
            records = session.run(
                "MATCH (r:Result {state: $state}) RETURN r ORDER BY r.run_timestamp DESC",
                state=state,
            ).data()
        else:
            records = session.run(
                "MATCH (r:Result) RETURN r ORDER BY r.run_timestamp DESC"
            ).data()
        results = [dict(r["r"]) for r in records]

        for r in results:
            script_rel = session.run(
                "MATCH (r:Result {artifact_id: $id})-[:GENERATED_BY]->(:Script) RETURN r LIMIT 1",
                id=r["artifact_id"],
            ).single()
            r["has_script"] = script_rel is not None
            data_rel = session.run(
                "MATCH (r:Result {artifact_id: $id})-[:COMPUTED_FROM]->(:DataFile) RETURN r LIMIT 1",
                id=r["artifact_id"],
            ).single()
            r["has_data"] = data_rel is not None

    driver.close()

    if not results:
        click.echo("No results found.")
        return

    # NAME is the AD-028 token key and therefore the column a reader looks for
    # first; a Result registered before AD-028 shows '-'.
    click.echo(f"{'ID':10} {'NAME':28} {'VALUE':10} {'UNITS':12} {'STATE':12} {'SCRIPT':7} {'DATA':5} DESCRIPTION")
    click.echo("-" * 110)
    for r in results:
        rid = r.get("artifact_id", "?")[:8]
        rname = (r.get("name") or "-")[:27]
        val = str(r.get("value", "?"))[:9]
        units = (r.get("units") or "")[:11]
        st = (r.get("state") or "?")[:11]
        has_s = "yes" if r.get("has_script") else "no"
        has_d = "yes" if r.get("has_data") else "no"
        desc = (r.get("description") or "")[:30]
        click.echo(f"{rid:<10} {rname:<28} {val:<10} {units:<12} {st:<12} {has_s:<7} {has_d:<5} {desc}")


@result_group.command("trace")
@click.argument("result_id")
def result_trace(result_id):
    """Show full provenance chain for a Result (upstream + downstream citations)."""
    config = load_project_config()
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]

    with driver.session(database=database) as session:
        node = get_artifact(session, result_id)
        if node is None:
            click.echo(f"Error: Result '{result_id}' not found", err=True)
            driver.close()
            raise SystemExit(1)

        upstream = get_provenance_chain(session, result_id)
        downstream = session.run(
            "MATCH (s:PaperSection)-[:CITES]->(r:Result {artifact_id: $id}) RETURN s",
            id=result_id,
        ).data()
        cited_by = [dict(r["s"]) for r in downstream]

    driver.close()

    val = node.get("value", "?")
    units = node.get("units", "")
    click.echo(f"\nResult: {result_id}")
    click.echo(f"  value: {val} {units}  state: {node.get('state', '?')}")

    if upstream:
        click.echo(f"\nProvenance (upstream):")
        for a in upstream:
            atype = a.get("artifact_type", "?")
            aid = a.get("artifact_id", "?")[:8]
            astate = a.get("state", "?")
            click.echo(f"  ← [{atype}] {aid}... ({astate})")
    else:
        click.echo("\nProvenance: none (no upstream links)")

    if cited_by:
        click.echo(f"\nCited by ({len(cited_by)} sections):")
        for s in cited_by:
            sid = s.get("artifact_id", "?")[:8]
            sstate = s.get("state", "?")
            click.echo(f"  → [PaperSection] {sid}... ({sstate})")
    else:
        click.echo("\nCited by: no sections")


@result_group.command("check-stale")
def result_check_stale():
    """List stale Results and what downstream artifacts they block."""
    config = load_project_config()
    driver = get_neo4j_driver(config)
    database = config["neo4j"]["database"]

    with driver.session(database=database) as session:
        stale = get_stale_artifacts(session)

        if not stale:
            click.echo("No stale results.")
            driver.close()
            return

        click.echo(f"Stale Results ({len(stale)}):\n")
        for r in stale:
            rid = r.get("artifact_id", "?")
            val = r.get("value", "?")
            units = r.get("units", "")
            click.echo(f"  ⚠ {rid[:8]}...  value={val} {units}")

            dependents = get_dependents(session, rid)
            if dependents:
                for d in dependents:
                    dtype = d.get("artifact_type", "?")
                    did = d.get("artifact_id", "?")[:8]
                    dstate = d.get("state", "?")
                    click.echo(f"      blocks: [{dtype}] {did}... ({dstate})")

    driver.close()


# ---------------------------------------------------------------------------
# AD-028 — migration of units-as-name Results
# ---------------------------------------------------------------------------

def collect_token_keys(project_dir: Path) -> set[str]:
    """Collect every name referenced by a {{result:NAME:field}} token on disk.

    Scans the project's paper sources. A units string that is ALSO used as a
    token key cannot be classified automatically: it is simultaneously a
    plausible unit and a live reference, which is the `ambiguous` class.

    Args:
        project_dir: Project root containing a `paper/` directory. A project
            with no paper directory yields an empty set.

    Returns:
        Set of names appearing in result reference tokens.

    Raises:
        OSError: If a discovered markdown file cannot be read. Unreadable
            source is not silently treated as "no tokens" — that would
            misclassify Results.
    """
    paper_dir = project_dir / "paper"
    if not paper_dir.is_dir():
        return set()

    keys: set[str] = set()
    for md_file in sorted(paper_dir.rglob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        for reftype, name, _field in REFERENCE_PATTERN.findall(text):
            if reftype == "result":
                keys.add(name)
    return keys


@dataclass
class Classification:
    """One Result's placement in an AD-028 migration class.

    Attributes:
        node: The Result node as read from the graph.
        migration_class: One of MIGRATION_CLASSES.
        reason: Why this class, in words, for the report.
        planned_action: What the live run would do to this row — one of
            ``set_name_and_clear_units``, ``clear_units`` or ``none``. The
            dry-run prints it and the live run executes it; they read the same
            field off the same plan, which is what makes the dry run
            predictive.
        new_name: The name the live run would assign, for the
            ``set_name_and_clear_units`` action. None for every other action.
    """
    node: dict
    migration_class: str
    reason: str
    planned_action: str = "none"
    new_name: Optional[str] = None


def classify_unnamed_results(
    results: list[dict],
    vocabulary: frozenset,
    token_keys: set[str],
    claimed_names: Optional[set[str]] = None,
) -> list[Classification]:
    """Sort Results that have no `name` into the AD-028 migration classes.

    Args:
        results: Result nodes with no `name` property.
        vocabulary: Strings that count as real units of measurement.
        token_keys: Names referenced by {{result:NAME:field}} tokens in the
            project's paper sources.
        claimed_names: Names already carried by other Results in this graph.
            A promotion into one of these would break uniqueness.

    Returns:
        One Classification per input Result, in input order. The classes:

        - ``ambiguous``: cannot be assigned automatically. Either the units
          string is a real unit that is ALSO in use as a token key, or
          promoting it would produce a duplicate `name` — because several
          unnamed Results share that units string, or a named Result already
          holds it. Result names are unique per graph, so a contested string
          is not assignable without a human deciding who gets it.
        - ``units_is_real_unit``: units is a real unit and nothing contests it.
          Leave `name` unset; report only.
        - ``refused``: units would be promoted, but the resulting name fails
          `validate_result_name` — bad grammar, empty, or over length. This is
          the class the original implementation was missing: the live path
          validated and the dry run did not, so the dry run predicted 3529
          migrations where the live run wrote 2576 and refused 953. The check
          now lives here, on the shared classification path, so a dry run
          cannot disagree with the live run about it.
        - ``migrated``: units is present, is not a real unit, is a valid name,
          and is uncontested — promote it to `name`.
        - ``no_units``: no name and no units. Nothing is inferable.

    Raises:
        Nothing.
    """
    claimed = claimed_names or set()

    # Count how many unnamed Results would propose each candidate name. A count
    # above one is a collision, not a migration.
    proposals: dict[str, int] = {}
    for node in results:
        units = node.get("units")
        if isinstance(units, str) and units.strip():
            proposals[units] = proposals.get(units, 0) + 1

    classifications: list[Classification] = []
    for node in results:
        units = node.get("units")

        if not isinstance(units, str) or not units.strip():
            classifications.append(Classification(
                node, "no_units",
                "no name and no units — nothing to promote",
            ))
            continue

        # Vocabulary first. A real unit is never promoted, so a repeated one is
        # not a name collision — several Results measured in `count` is normal.
        if units in vocabulary:
            if units in token_keys:
                classifications.append(Classification(
                    node, "ambiguous",
                    f"units {units!r} is a real unit AND is in use as a "
                    f"{{{{result:...}}}} token key",
                ))
            else:
                classifications.append(Classification(
                    node, "units_is_real_unit",
                    f"units {units!r} is a real unit of measurement",
                ))
            continue

        # The grammar check the live path applies, applied here so the dry run
        # applies it too. A string that cannot be a name is refused whether or
        # not anything contests it.
        try:
            validate_result_name(units)
        except ValueError as exc:
            classifications.append(Classification(
                node, "refused", str(exc),
            ))
            continue

        # Only the promote branch can collide: `name` is unique per graph.
        contested_count = proposals.get(units, 0)
        if contested_count > 1:
            classifications.append(Classification(
                node, "ambiguous",
                f"units {units!r} is shared by {contested_count} unnamed Results; "
                f"promoting it would break name uniqueness",
            ))
            continue
        if units in claimed:
            classifications.append(Classification(
                node, "ambiguous",
                f"units {units!r} is already claimed as another Result's name",
            ))
            continue

        classifications.append(Classification(
            node, "migrated",
            f"units {units!r} is not a real unit — it is a token key in the "
            f"wrong property",
            planned_action="set_name_and_clear_units",
            new_name=units,
        ))

    return classifications


def build_migration_plan(
    results: list[dict],
    vocabulary: frozenset,
    token_keys: set[str],
) -> list[Classification]:
    """Classify *every* Result in the graph into exactly one migration class.

    This is the single plan both `--dry-run` and the live run consume. The dry
    run prints it; the live run executes the `planned_action` on it. Neither
    path re-derives anything, which is the structural fix for the defect
    recorded in AD-028 Amendment 01:

        A dry run that does not execute every validation the live path
        executes is not a dry run.

    Args:
        results: Every Result node in the project graph, in report order.
        vocabulary: Strings that count as real units of measurement.
        token_keys: Names referenced by {{result:NAME:field}} tokens on disk.

    Returns:
        One Classification per input Result, in input order. Results that
        already carry a `name` are handled here (they are what makes the
        command resumable); the rest are delegated to
        `classify_unnamed_results`.

        A named Result whose `units` still holds the same string is
        ``name_set_units_pending``: an earlier migration set the name but its
        compensating `units` clear never landed. Its planned action is
        ``clear_units`` — never a re-assignment of the name it already has.

    Raises:
        Nothing.
    """
    named_idx: list[int] = []
    unnamed_idx: list[int] = []
    for i, node in enumerate(results):
        name = node.get("name")
        (named_idx if isinstance(name, str) and name else unnamed_idx).append(i)

    claimed_names = {results[i]["name"] for i in named_idx}

    plan: list[Optional[Classification]] = [None] * len(results)

    for i in named_idx:
        node = results[i]
        name = node["name"]
        units = node.get("units")
        if isinstance(units, str) and units == name:
            plan[i] = Classification(
                node, "name_set_units_pending",
                f"name {name!r} is already set but units still holds the same "
                f"string — the units clear from an earlier migration never "
                f"landed",
                planned_action="clear_units",
            )
        else:
            plan[i] = Classification(
                node, "already_named",
                f"name {name!r} is already set — skipped",
            )

    unnamed = [results[i] for i in unnamed_idx]
    for i, classification in zip(
        unnamed_idx,
        classify_unnamed_results(
            unnamed, vocabulary, token_keys, claimed_names=claimed_names
        ),
    ):
        plan[i] = classification

    # Every index was assigned by one of the two loops above; the assertion
    # states that invariant rather than trusting it.
    if any(item is None for item in plan):
        raise RuntimeError(
            "build_migration_plan left a Result unclassified — this is a bug"
        )
    return [item for item in plan if item is not None]


def write_migration_report(path: Path, plan: list[Classification]) -> None:
    """Write the per-row migration plan as JSONL.

    The field set is MIGRATION_REPORT_FIELDS and is a consumed contract; see
    that constant. One JSON object per line, in plan order, one line per
    Result in the graph — including rows the run will not touch, so a consumer
    can reconcile the file against the graph's total row count.

    Args:
        path: Destination file. Parent directories are created.
        plan: The plan from `build_migration_plan`.

    Returns:
        None.

    Raises:
        OSError: If the file cannot be written. Not caught — a report the
            caller asked for and did not get is a failure, not a warning.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in plan:
            row = {
                "artifact_id": item.node.get("artifact_id"),
                "current_name": item.node.get("name"),
                "current_units": item.node.get("units"),
                "class": item.migration_class,
                "planned_action": item.planned_action,
                "reason": item.reason,
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _describe_result(node: dict) -> str:
    """One-line description of a Result for the migration report."""
    return (
        f"{node.get('artifact_id', '?')}  name={node.get('name')!r}  "
        f"units={node.get('units')!r}  value={node.get('value')!r}  "
        f"state={node.get('state')!r}"
    )


@result_group.command("migrate-names")
@click.option("--dry-run", is_flag=True, default=False,
              help="Build and report the plan without writing any event. The "
                   "dry run applies every validation the live run applies and "
                   "exits with the same code, so its report predicts the live "
                   "outcome exactly.")
@click.option("--partial", "partial", is_flag=True, default=False,
              help="Write the valid rows even when the plan contains refusals. "
                   "Without it a single refusal aborts the whole run and "
                   "nothing at all is written. Either way the run still exits "
                   "non-zero when anything was refused.")
@click.option("--report", "report_path", default=None,
              type=click.Path(dir_okay=False),
              help="Write the per-row plan to PATH as JSONL — one object per "
                   "Result in the graph, with artifact_id, current_name, "
                   "current_units, class, planned_action and reason. Works "
                   "with and without --dry-run.")
@click.option("--project-dir", "project_dir_opt", default=None,
              type=click.Path(exists=True, file_okay=False),
              help="Project root to migrate. Defaults to the current directory.")
@click.option("--show-all", is_flag=True, default=False,
              help="List every Result in every class. Without it, only the "
                   "refused and ambiguous classes are listed in full.")
def result_migrate_names(dry_run, partial, report_path, project_dir_opt, show_all):
    """Promote units-as-name Results to a real `name` property (AD-028).

    Before AD-028 `seldon result register` had no --name flag, so token keys
    were stashed in `units`. This walks every Result in the graph, builds one
    plan classifying each row (see MIGRATION_CLASSES), and — outside --dry-run
    — executes that plan's actions as `artifact_updated` events. Migration is
    by event; nothing is mutated directly.

    Three properties, each pinned by a test:

    **Predictive.** `--dry-run` and the live run consume the same plan from the
    same `build_migration_plan` call, so the dry run applies every validation
    the live path applies and exits with the same code. AD-028 Amendment 01
    records why: the first implementation validated only on the live path, so
    the dry run promised 3529 migrations and the live run wrote 2576 and
    refused 953 partway through.

    **Atomic.** Validate-all-then-write. Any row in the `refused` class aborts
    the whole run with nothing written, unless --partial is passed, in which
    case the valid rows are written and the refusals are left untouched. Both
    forms exit non-zero when anything was refused.

    **Resumable.** A Result that already carries a `name` is never renamed. If
    its `units` still holds that same string — a half-applied earlier run whose
    compensating clear never landed — it is classified
    `name_set_units_pending` and gets the `units` clear event only.
    """
    project_dir = Path(project_dir_opt) if project_dir_opt else Path.cwd()
    config = load_project_config(project_dir)
    database = config["neo4j"]["database"]
    driver = get_neo4j_driver(config)
    session_id = get_current_session(project_dir)

    try:
        vocabulary = load_units_vocabulary()

        # Every Result, not just the unnamed ones: named rows are what the
        # resumability and `name_set_units_pending` classes are about, and a
        # plan that omits them cannot reconcile against the graph's row count.
        with driver.session(database=database) as sess:
            results = [
                dict(r["r"]) for r in sess.run(
                    "MATCH (r:Result) RETURN r ORDER BY r.created_at ASC"
                ).data()
            ]

        token_keys = collect_token_keys(project_dir)
        plan = build_migration_plan(results, vocabulary, token_keys)

        buckets: dict[str, list[Classification]] = {c: [] for c in MIGRATION_CLASSES}
        for item in plan:
            buckets[item.migration_class].append(item)

        mode = "DRY RUN" if dry_run else "LIVE"
        click.echo(f"Result name migration — database '{database}' ({mode})")
        click.echo(f"  Results in graph: {len(results)}")
        for cls in MIGRATION_CLASSES:
            click.echo(f"    {cls:<24} {len(buckets[cls])}")
        click.echo()

        if report_path:
            destination = Path(report_path)
            write_migration_report(destination, plan)
            click.echo(
                f"Wrote the per-row plan for {len(plan)} Result(s) to {destination}"
            )
            click.echo()

        refused = buckets["refused"]
        ambiguous = buckets["ambiguous"]

        # Refused and ambiguous are always listed in full: both need a human,
        # and truncating the list is how a refusal goes unnoticed.
        click.echo(
            f"refused ({len(refused)}) — cannot become a name, nothing written:"
        )
        for item in refused:
            click.echo(f"  {_describe_result(item.node)}")
            click.echo(f"      {item.reason}")
        click.echo()

        click.echo(f"ambiguous ({len(ambiguous)}) — not assigned, needs a human:")
        for item in ambiguous:
            click.echo(f"  {_describe_result(item.node)}")
            click.echo(f"      {item.reason}")
        click.echo()

        for cls in ("units_is_real_unit", "no_units", "already_named"):
            items = buckets[cls]
            click.echo(f"{cls} ({len(items)}):")
            shown = items if show_all else items[:MIGRATION_REPORT_PREVIEW]
            for item in shown:
                click.echo(f"  {_describe_result(item.node)}")
            if len(shown) < len(items):
                click.echo(f"  ... and {len(items) - len(shown)} more (--show-all)")
            click.echo()

        pending = buckets["name_set_units_pending"]
        click.echo(
            f"name_set_units_pending ({len(pending)}) — units cleared, name left as is:"
        )
        shown = pending if show_all else pending[:MIGRATION_REPORT_PREVIEW]
        for item in shown:
            click.echo(
                f"  {item.node.get('artifact_id', '?')}  "
                f"name={item.node.get('name')!r} (kept)  units := null"
            )
        if len(shown) < len(pending):
            click.echo(f"  ... and {len(pending) - len(shown)} more (--show-all)")
        click.echo()

        to_migrate = buckets["migrated"]
        click.echo(f"migrated ({len(to_migrate)}) — name := units, units cleared:")
        shown = to_migrate if show_all else to_migrate[:MIGRATION_REPORT_PREVIEW]
        for item in shown:
            click.echo(
                f"  {item.node.get('artifact_id', '?')}  "
                f"name := {item.new_name!r}"
            )
        if len(shown) < len(to_migrate):
            click.echo(f"  ... and {len(to_migrate) - len(shown)} more (--show-all)")
        click.echo()

        writable = [
            item for item in plan
            if item.migration_class in MIGRATION_WRITING_CLASSES
        ]

        # Invariant, not a re-validation: build_migration_plan sends every
        # contested string to `ambiguous`, so no two writable rows may claim
        # the same name. Stating it here turns a silent uniqueness violation
        # into a crash before any event is written.
        proposed = [item.new_name for item in writable if item.new_name is not None]
        if len(proposed) != len(set(proposed)):
            raise RuntimeError(
                "migration plan proposes the same name twice — this is a bug "
                "in build_migration_plan, not a data problem"
            )

        blocked = bool(refused) and not partial

        if dry_run:
            click.echo("Dry run — no events written.")
            if blocked:
                click.echo(
                    f"The live run would REFUSE to write anything: "
                    f"{len(refused)} row(s) fail validation and --partial was "
                    f"not passed. Predicted live exit code: 1.",
                    err=True,
                )
                raise SystemExit(1)
            click.echo(
                f"The live run would write {len(writable)} event(s): "
                f"{len(to_migrate)} promotion(s) and {len(pending)} units clear(s)."
            )
            if refused:
                click.echo(
                    f"With --partial it would still exit 1: {len(refused)} "
                    f"row(s) refused.", err=True,
                )
                raise SystemExit(1)
            return

        if blocked:
            click.echo(
                f"Refusing to write: {len(refused)} of {len(plan)} Result(s) "
                f"fail validation. NOTHING was written. Fix the offending rows, "
                f"or pass --partial to write the {len(writable)} valid row(s) "
                f"and leave the refusals in place.",
                err=True,
            )
            for item in refused:
                click.echo(
                    f"  {item.node.get('artifact_id', '?')}: {item.reason}", err=True
                )
            raise SystemExit(1)

        promoted = 0
        cleared = 0
        for item in writable:
            artifact_id = item.node.get("artifact_id", "?")
            # One combined event: `seldon/core/sync.py` projects events by
            # event_type and skips types it does not know, so a bespoke
            # result_name_assigned / result_units_cleared pair would vanish on
            # replay. `artifact_updated` replays correctly, and a null property
            # value removes the key in Neo4j, so the clear survives too.
            if item.planned_action == "set_name_and_clear_units":
                properties = {"name": item.new_name, "units": None}
            else:
                properties = {"units": None}
            update_artifact(
                project_dir=project_dir, driver=driver, database=database,
                artifact_id=artifact_id,
                properties=properties,
                actor="cc", authority="accepted", session_id=session_id,
            )
            if item.planned_action == "set_name_and_clear_units":
                promoted += 1
            else:
                cleared += 1

        click.echo(f"Migrated {promoted} Result(s).")
        click.echo(f"Cleared pending units on {cleared} Result(s).")
        if refused:
            click.echo(
                f"Refused {len(refused)} (written anyway under --partial: "
                f"{len(writable)}):", err=True,
            )
            for item in refused:
                click.echo(
                    f"  {item.node.get('artifact_id', '?')}: {item.reason}", err=True
                )
            raise SystemExit(1)
    finally:
        driver.close()


# ---------------------------------------------------------------------------
# AD-028 — provenance backfill
# ---------------------------------------------------------------------------

def load_provenance_map(map_path: Path) -> dict[str, dict[str, Any]]:
    """Load and shape-check a backfill map file.

    Args:
        map_path: Path to a YAML or JSON file of shape
            ``{result_name_or_id: {computed_from: [names], generated_by: name}}``.
            A ``.json`` suffix is parsed as JSON; anything else as YAML (which
            also accepts JSON).

    Returns:
        The parsed mapping.

    Raises:
        ValueError: If the file does not parse to a mapping, if a row is not a
            mapping, if a row carries an unknown key, if ``computed_from`` is
            not a list of non-empty strings, or if ``generated_by`` is not a
            non-empty string.
        OSError: If the file cannot be read.
    """
    text = map_path.read_text(encoding="utf-8")
    if map_path.suffix.lower() == ".json":
        parsed = json.loads(text)
    else:
        parsed = yaml.safe_load(text)

    if not isinstance(parsed, dict):
        raise ValueError(
            f"{map_path}: expected a mapping of result → provenance, "
            f"got {type(parsed).__name__}"
        )

    allowed = {"computed_from", "generated_by"}
    for key, row in parsed.items():
        if not isinstance(row, dict):
            raise ValueError(
                f"{map_path}: row '{key}' must be a mapping with keys "
                f"{sorted(allowed)}, got {type(row).__name__}"
            )
        unknown = set(row) - allowed
        if unknown:
            raise ValueError(
                f"{map_path}: row '{key}' has unknown key(s) {sorted(unknown)}; "
                f"allowed keys are {sorted(allowed)}"
            )
        cf = row.get("computed_from")
        if cf is not None:
            if not isinstance(cf, list) or not all(
                isinstance(v, str) and v.strip() for v in cf
            ):
                raise ValueError(
                    f"{map_path}: row '{key}' computed_from must be a list of "
                    f"non-empty DataFile names"
                )
        gb = row.get("generated_by")
        if gb is not None and (not isinstance(gb, str) or not gb.strip()):
            raise ValueError(
                f"{map_path}: row '{key}' generated_by must be a non-empty "
                f"Script name"
            )

    return parsed


def _link_exists(session, from_id: str, to_id: str, rel_type: str) -> bool:
    """Return True if a relationship of this type already joins the two nodes."""
    record = session.run(
        f"MATCH (a:Artifact {{artifact_id: $from_id}})"
        f"-[r:{rel_type}]->"
        f"(b:Artifact {{artifact_id: $to_id}}) RETURN r LIMIT 1",
        from_id=from_id, to_id=to_id,
    ).single()
    return record is not None


@result_group.command("backfill-provenance")
@click.option("--map", "map_file", required=True,
              type=click.Path(exists=True, dir_okay=False),
              help="YAML or JSON file: {result_name_or_id: {computed_from: [names], "
                   "generated_by: name}}")
@click.option("--dry-run", is_flag=True, default=False,
              help="Resolve and report the planned links without writing events.")
@click.option("--project-dir", "project_dir_opt", default=None,
              type=click.Path(exists=True, file_okay=False),
              help="Project root to write into. Defaults to the current directory.")
def result_backfill_provenance(map_file, dry_run, project_dir_opt):
    """Attach computed_from / generated_by links to existing Results (AD-028).

    Each row is resolved in full before any of its links are written. A row
    naming an unknown Result, DataFile, or Script fails as a whole, is reported,
    and the remaining rows still run; the command exits non-zero if any row
    failed.
    """
    project_dir = Path(project_dir_opt) if project_dir_opt else Path.cwd()
    config = load_project_config(project_dir)
    database = config["neo4j"]["database"]
    domain_config = _get_domain_config(config)
    driver = get_neo4j_driver(config)
    session_id = get_current_session(project_dir)

    try:
        try:
            provenance_map = load_provenance_map(Path(map_file))
        except (ValueError, json.JSONDecodeError, yaml.YAMLError) as e:
            click.echo(f"Error: {e}", err=True)
            raise SystemExit(1)

        planned: list[tuple[str, str, str, str]] = []  # (result_id, target_id, rel, label)
        failed_rows: dict[str, list[str]] = {}

        for row_key, row in provenance_map.items():
            problems: list[str] = []

            with driver.session(database=database) as sess:
                result_node = find_result_by_name(sess, row_key)
                if result_node is None:
                    candidate = get_artifact(sess, row_key)
                    if candidate is not None and candidate.get("artifact_type") == "Result":
                        result_node = candidate
            if result_node is None:
                problems.append(
                    f"no Result with name or artifact_id '{row_key}'"
                )

            row_links: list[tuple[str, str, str, str]] = []

            for dname in row.get("computed_from") or []:
                with driver.session(database=database) as sess:
                    node = find_artifact_by_property(sess, "DataFile", "name", dname)
                if node is None:
                    problems.append(f"no DataFile named '{dname}'")
                elif result_node is not None:
                    row_links.append((
                        result_node["artifact_id"], node["artifact_id"],
                        "computed_from", f"COMPUTED_FROM {dname}",
                    ))

            sname = row.get("generated_by")
            if sname:
                with driver.session(database=database) as sess:
                    node = find_artifact_by_property(sess, "Script", "name", sname)
                if node is None:
                    problems.append(f"no Script named '{sname}'")
                elif result_node is not None:
                    row_links.append((
                        result_node["artifact_id"], node["artifact_id"],
                        "generated_by", f"GENERATED_BY {sname}",
                    ))

            if problems:
                failed_rows[row_key] = problems
                continue
            planned.extend(row_links)

        mode = "DRY RUN" if dry_run else "LIVE"
        click.echo(f"Provenance backfill — database '{database}' ({mode})")
        click.echo(f"  rows: {len(provenance_map)}  "
                   f"ok: {len(provenance_map) - len(failed_rows)}  "
                   f"failed: {len(failed_rows)}")
        click.echo()

        written = 0
        skipped = 0
        for result_id, target_id, rel_type, label in planned:
            with driver.session(database=database) as sess:
                already = _link_exists(sess, result_id, target_id, rel_type.upper())
            if already:
                click.echo(f"  = {result_id[:8]}... {label} (already linked)")
                skipped += 1
                continue
            if dry_run:
                click.echo(f"  + {result_id[:8]}... {label}")
                continue
            to_type = "DataFile" if rel_type == "computed_from" else "Script"
            create_link(
                project_dir=project_dir, driver=driver, database=database,
                domain_config=domain_config,
                from_id=result_id, to_id=target_id,
                from_type="Result", to_type=to_type,
                rel_type=rel_type, actor="cc", authority="accepted",
                session_id=session_id,
            )
            click.echo(f"  + {result_id[:8]}... {label}")
            written += 1

        click.echo()
        if dry_run:
            click.echo(f"Dry run — {len(planned) - skipped} link(s) would be written, "
                       f"{skipped} already present. No events written.")
        else:
            click.echo(f"Wrote {written} link event(s); {skipped} already present.")

        if failed_rows:
            click.echo(f"\nFailed rows ({len(failed_rows)}):", err=True)
            for row_key, problems in failed_rows.items():
                for problem in problems:
                    click.echo(f"  {row_key}: {problem}", err=True)
            raise SystemExit(1)
    finally:
        driver.close()
