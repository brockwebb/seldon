"""LINT: no Seldon Cypher may bind a node with no label (task 2026-09-07 §3).

Adapted from ai-readiness-kg's `tests/test_cypher_unlabelled_lint.py`
(`230b282f` §1.2), which was written after that repo shipped the same defect
twice. Seldon's version of the defect is the co-tenancy one, not the twin-node
one: a project database may hold a domain knowledge graph beside the Seldon
artifact graph, under disjoint labels. `MATCH (a)-[r:PRECEDES]->(b)` then reads
the domain KG's `precedes` edges (ai-readiness-kg whitelists `precedes:
Concept → Concept`, BFO_0000063) as if they were task ordering, and readiness
becomes unanswerable — 117 `? [missing] → ? [missing]` rows in `seldon verify`.

The rule this enforces is AD-029's addendum: **Seldon never reads a
relationship by name alone.** Every node pattern in every Seldon query names a
label, so that a query can only ever see nodes Seldon authored.

It is a grep, deliberately. A lint that understood Cypher would be a dependency
and a second thing to be wrong. What it does understand is Python: queries are
recovered from the AST rather than by regex, so an f-string, an implicitly
concatenated string and a `+`-joined string are all checked as the one query
they become at runtime.

A variable that carries a label *anywhere* in the same query is bound for the
whole query — `MATCH (a:Artifact) ... MERGE (a)-[r:X]->(b:Artifact)` is fine,
because `a` was labelled where it was introduced.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: Every package whose Cypher is linted. `seldon/paper/` is included because a
#: co-tenanted database is no less co-tenanted when the manuscript pipeline
#: reads it.
LINTED_ROOTS = ("seldon/core", "seldon/commands", "seldon/paper")

#: A string is treated as a query if it opens with a Cypher reading or writing
#: clause. Anchoring at the start is what keeps module docstrings that merely
#: quote a query (`seldon/commands/rebuild.py`) out of the lint.
_IS_QUERY = re.compile(r"^\s*(MATCH|OPTIONAL MATCH|MERGE|CREATE|UNWIND|WITH)\b")

#: A node pattern: an opening paren that is not a function call — i.e. not
#: preceded by an identifier character, a `)` or a `]` — holding an optional
#: variable and then a label (`:`), a property map (`{`) or nothing (`)`).
_NODE = re.compile(r"(?<![\w)\]])\(\s*(?:([A-Za-z_][A-Za-z0-9_]*)\s*)?(:|\{|\))")

#: The same pattern, restricted to the labelled form, to collect bound variables.
_LABELLED = re.compile(r"(?<![\w)\]])\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*:")

#: Queries allowed to bind a node with no label, each with the reason it cannot
#: carry one. Keep this list SHORT and specific: an entry is a standing
#: co-tenancy risk that someone decided to accept, not a dismissal. Matched as a
#: substring of the normalised (whitespace-collapsed) query.
ALLOW: dict[str, str] = {
    # `seldon.core.precedence.read_half_artifact_edges` — the one query whose
    # whole job is to find `precedes` edges that straddle the Seldon graph and a
    # co-tenant's. Binding `:Artifact` on both ends would make it return
    # nothing, and the straddling edge is exactly the illegal edge that the bind
    # on `read_edges` would otherwise hide instead of fixing. The `labels()`
    # predicate on both endpoints is what keeps it honest: it names the label it
    # is reasoning about rather than ignoring labels.
    "WHERE ('Artifact' IN labels(a)) <> ('Artifact' IN labels(b))":
        "reads edges that straddle the Seldon graph and a co-tenant, by design",
}


def _flatten(node: ast.AST) -> str | None:
    """Reconstruct a string expression, or None if it is not one.

    Handles the three ways a query reaches `session.run`: a plain (possibly
    implicitly concatenated) literal, an f-string, and a `+`-joined chain of
    either. An interpolated slot becomes the placeholder ``INTERP`` — which is
    exactly right for a label, because ``f"(t:{ARTIFACT_TYPE})"`` reads as
    ``(t:INTERP)`` and is labelled.
    """
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            else:
                parts.append("INTERP")
        return "".join(parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _flatten(node.left), _flatten(node.right)
        if left is None or right is None:
            return None
        return left + right
    return None


def _queries(path: Path) -> list[tuple[int, str]]:
    """Every Cypher query in a module, as (line number, normalised text).

    Two shapes are collected: the argument of a `.run(...)` call, and any
    assignment whose target is named like a query (`cypher`, `query`). Between
    them they cover every way Seldon issues Cypher; a string that is neither is
    prose, not a query.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[tuple[int, str]] = []

    def take(node: ast.AST) -> None:
        text = _flatten(node)
        if text and _IS_QUERY.match(text):
            found.append((node.lineno, " ".join(text.split())))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "run" and node.args:
                take(node.args[0])
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = {t.id for t in targets if isinstance(t, ast.Name)}
            if names & {"cypher", "query"} and node.value is not None:
                take(node.value)

    return found


def _offending_patterns(query: str) -> list[str]:
    """Node patterns in ``query`` that name no label and bind no labelled variable."""
    bound = set(_LABELLED.findall(query))
    offenders = []
    for match in _NODE.finditer(query):
        variable, kind = match.group(1), match.group(2)
        if kind == ":":
            continue
        if variable and variable in bound:
            continue
        offenders.append(match.group(0))
    return offenders


def _linted_files() -> list[Path]:
    files: list[Path] = []
    for root in LINTED_ROOTS:
        files.extend((REPO / root).rglob("*.py"))
    return sorted(files)


def test_linted_roots_exist_and_hold_queries():
    """Guard the paths: a typo in LINTED_ROOTS would make the lint vacuously pass."""
    files = _linted_files()
    assert files, f"no Python files under {LINTED_ROOTS}"
    total = sum(len(_queries(path)) for path in files)
    assert total > 50, f"only {total} queries found — the collector is not seeing them"


def test_no_seldon_query_binds_a_node_without_a_label():
    offenders = []
    for path in _linted_files():
        for lineno, query in _queries(path):
            bad = _offending_patterns(query)
            if not bad:
                continue
            if any(allowed in query for allowed in ALLOW):
                continue
            offenders.append(
                f"{path.relative_to(REPO)}:{lineno}: {bad} in {query[:110]}"
            )
    assert not offenders, (
        "unlabelled node pattern in a Seldon query — in a co-tenanted project "
        "database this reads the domain KG's nodes as Seldon artifacts "
        "(AD-029 addendum: never read a relationship by name alone):\n  "
        + "\n  ".join(offenders)
    )


def test_the_lint_would_catch_the_defect_it_was_written_for():
    """Mutation guard: the lint has to fail on the exact query that shipped."""
    bad = (
        "MATCH (a)-[r:PRECEDES]->(b) RETURN a.artifact_id AS from_id, "
        "b.artifact_id AS to_id"
    )
    assert _IS_QUERY.match(bad)
    assert _offending_patterns(bad) == ["(a)", "(b)"]
    assert not any(allowed in bad for allowed in ALLOW)


def test_the_lint_accepts_the_labelled_form_that_fixes_it():
    good = (
        "MATCH (a:Artifact)-[r:PRECEDES]->(b:Artifact) "
        "RETURN a.artifact_id AS from_id, b.artifact_id AS to_id"
    )
    assert _offending_patterns(good) == []


def test_a_variable_labelled_once_is_bound_for_the_whole_query():
    """The `MERGE` half of an ontology replica write must not be flagged."""
    query = (
        "MATCH (a:Artifact:OntologyTerm {term_id: $from_id}), "
        "(b:Artifact:OntologyTerm {term_id: $to_id}) "
        "MERGE (a)-[r:REFERENCES]->(b) RETURN r"
    )
    assert _offending_patterns(query) == []


def test_function_calls_are_not_mistaken_for_node_patterns():
    """`count(r)`, `type(r)` and `labels(n)` are calls, not unlabelled nodes."""
    query = (
        "MATCH (a:Artifact)-[r]->(b:Artifact) WHERE NONE(l IN labels(a) "
        "WHERE l IN $internal) RETURN type(r) AS rel, count(r) AS cnt"
    )
    assert _offending_patterns(query) == []


def test_anonymous_and_property_bound_nodes_are_both_caught():
    assert _offending_patterns("MATCH ()-[r]->() RETURN type(r)") == ["()", "()"]
    assert _offending_patterns(
        "MATCH (a {artifact_id: $id})-[r]->(b:Artifact) RETURN r"
    ) == ["(a {"]


def test_prose_that_quotes_a_query_is_not_linted():
    """`seldon/commands/rebuild.py`'s docstring warns about the wipe it performs."""
    docstring = (
        "Rebuild Neo4j graph from JSONL event log. WARNING: This issues "
        "MATCH (n) DETACH DELETE n on the PROJECT database."
    )
    assert not _IS_QUERY.match(docstring)
