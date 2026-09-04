"""Legacy event-log records: deterministic ids and shape normalisation.

Why this module exists
----------------------
`seldon_events.jsonl` is append-only and immutable. Early Seldon (before
`make_event` existed) wrote a *flat* record with no envelope: the payload
fields sat at the top level and there was no ``event_id``, no ``timestamp`` and
no ``session_id``. Nine such lines head `seldon-seldon-self`'s log.

`read_events` de-duplicates on ``event_id``. Two records whose id is ``None``
looked like a collision, so the very first read of the log raised
``DuplicateEventError`` and **no full replay was possible** — which broke
Recoverability, one of Seldon's declared guaranteed properties.

The fix cannot be "edit those nine lines". The log's immutability is the
substrate every provenance claim in the system rests on. So instead:

1. A **deterministic id** is *derived* from each legacy record. The log is
   never touched.
2. A ``legacy_event_id_assigned`` record is **appended** for each one, freezing
   the derivation in the log itself so it is auditable and tamper-evident.
3. `read_events` derives the same id on every read, so recoverability is
   restored whether or not the migration has run. The appended records are the
   audit trail and the tamper detector, not a lookup table `read_events`
   depends on — a lookup table would force a two-pass read and would make
   recoverability contingent on a migration having been run, which is exactly
   the fragility being removed.

The id recipe
-------------
``legacy-{ordinal:06d}-{sha256(canonical_json(record))[:32]}``

*Ordinal* is the 1-based index of the record among the successfully-parsed
records of the log (blank and malformed lines do not advance it, matching
`read_events`). Because the log is append-only, an existing record's ordinal
can never change.

*Canonical JSON* is ``json.dumps(record, sort_keys=True, ensure_ascii=True,
separators=(",", ":"))`` encoded UTF-8. The **parsed object** is hashed, not
the raw line, so reformatting the file (whitespace, key order, unicode
escaping) yields the same id: the id identifies the event's content, not its
serialisation.

Why it cannot collide with a real uuid4
---------------------------------------
Structurally, not probabilistically:

- A uuid4 string is exactly 36 characters; a legacy id is 46.
- A uuid4 string contains only ``[0-9a-f-]``; a legacy id begins with the
  literal ASCII ``legacy-``, and ``l``, ``g`` and ``y`` are not hex digits.

Either property alone is sufficient. No uuid4 can ever be mistaken for a legacy
id, and no legacy id can ever shadow a real one.

Why two legacy ids cannot collide with each other
-------------------------------------------------
The ordinal is a strictly increasing record index within one log, and it is
carried *in* the id. Two distinct records therefore have distinct ids by
construction, independently of the hash. The hash is not load-bearing for
uniqueness — it is load-bearing for **tamper evidence**: if a legacy line is
ever edited, its derived id changes and stops matching the
``legacy_event_id_assigned`` record frozen in the log. `seldon verify` reports
that as a failure.

(If two different projects' logs were ever concatenated, equal ordinals would
meet. The content hash then separates them — unless the content is identical
too, in which case they are genuinely the same record and collapsing them is
correct.)
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, List, Optional

#: Literal prefix that makes a derived id structurally un-confusable with uuid4.
LEGACY_EVENT_ID_PREFIX = "legacy-"

#: Number of hex characters of the sha256 digest carried in the id.
LEGACY_ID_DIGEST_CHARS = 32

#: Event type appended by the migration to record an id assignment.
LEGACY_ASSIGNMENT_EVENT_TYPE = "legacy_event_id_assigned"

#: Recipe version, stamped into every assignment record. If the derivation ever
#: has to change, old records stay interpretable because they say which recipe
#: produced them. Bumping this is a breaking change to derived ids and must be
#: accompanied by a new assignment pass, never a silent re-derivation.
LEGACY_ID_RECIPE_VERSION = 1

#: Keys that belong to the event *envelope*. Anything else at the top level of
#: a legacy record is payload that predates the envelope's existence.
ENVELOPE_KEYS = frozenset(
    {"event_id", "event_type", "timestamp", "session_id", "actor", "authority", "payload"}
)


def canonical_json(record: Dict[str, Any]) -> str:
    """Return the canonical JSON serialisation used for hashing.

    Args:
        record: The parsed event record.

    Returns:
        A deterministic JSON string: keys sorted (recursively), no insignificant
        whitespace, non-ASCII escaped so the byte sequence does not depend on
        the reader's encoding.
    """
    return json.dumps(record, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def content_digest(record: Dict[str, Any]) -> str:
    """Return the full sha256 hex digest of a record's canonical JSON.

    Args:
        record: The parsed event record, exactly as it appears in the log.

    Returns:
        64 lowercase hex characters.
    """
    return hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest()


def legacy_event_id(ordinal: int, record: Dict[str, Any]) -> str:
    """Derive the deterministic event id for a legacy record.

    Args:
        ordinal: 1-based index of the record among parsed records in the log.
        record: The parsed legacy record, exactly as it appears in the log.

    Returns:
        ``legacy-<ordinal:06d>-<sha256[:32]>``. See the module docstring for the
        collision argument.

    Raises:
        ValueError: If ``ordinal`` is not a positive integer. A zero or negative
            ordinal means the caller lost track of position in the log, and
            silently producing an id from it would freeze that mistake into the
            audit record.
    """
    if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 1:
        raise ValueError(f"ordinal must be a positive integer, got {ordinal!r}")
    digest = content_digest(record)[:LEGACY_ID_DIGEST_CHARS]
    return f"{LEGACY_EVENT_ID_PREFIX}{ordinal:06d}-{digest}"


def is_legacy_event_id(value: Any) -> bool:
    """Return True if ``value`` is a derived legacy id rather than a uuid4.

    Args:
        value: Candidate event id.

    Returns:
        True only for strings carrying the legacy prefix.
    """
    return isinstance(value, str) and value.startswith(LEGACY_EVENT_ID_PREFIX)


def is_legacy_record(record: Dict[str, Any]) -> bool:
    """Return True if ``record`` predates the event envelope.

    The test is the absence of a usable ``event_id``. That is the defect this
    module exists to repair, and it is the only property every legacy record is
    known to share. An explicit ``"event_id": null`` counts as absent.

    Args:
        record: A parsed record from the event log.

    Returns:
        True if the record needs a derived id.
    """
    return record.get("event_id") in (None, "")


def normalise_legacy_record(ordinal: int, record: Dict[str, Any]) -> Dict[str, Any]:
    """Return a legacy record in canonical envelope shape, with a derived id.

    Two repairs, both non-destructive (the input is not mutated and the log is
    not touched):

    1. **Id.** A deterministic ``event_id`` is derived — see the module
       docstring.
    2. **Shape.** Legacy records are *flat*: ``artifact_id``, ``to_state`` and
       friends sit at the top level, where every consumer since
       `seldon.core.sync._apply_event` looks for them under ``payload``. Those
       non-envelope keys are moved into ``payload``. Without this, a replay of a
       legacy line raises ``KeyError`` even once it has an id — an id alone does
       not restore recoverability.

    ``timestamp`` and ``session_id`` are set to ``None``, not invented. The
    legacy writer recorded neither; synthesising one would put a fabricated
    value into the provenance chain. ``None`` is the honest answer and no
    consumer in this codebase reads either field positionally.

    Args:
        ordinal: 1-based index of the record among parsed records in the log.
        record: The parsed legacy record.

    Returns:
        A new dict in canonical envelope shape with ``legacy: True`` set, so a
        consumer can tell a repaired record from a natively-written one.

    Raises:
        ValueError: If ``ordinal`` is not a positive integer.
    """
    payload = dict(record.get("payload") or {})
    for key, value in record.items():
        if key in ENVELOPE_KEYS:
            continue
        # A key already present under `payload` wins: an explicit payload is a
        # deliberate statement, a stray top-level twin is not.
        payload.setdefault(key, value)

    return {
        "event_id": legacy_event_id(ordinal, record),
        "event_type": record.get("event_type"),
        "timestamp": record.get("timestamp"),
        "session_id": record.get("session_id"),
        "actor": record.get("actor"),
        "authority": record.get("authority"),
        "payload": payload,
        "legacy": True,
    }


def make_assignment_payload(ordinal: int, record: Dict[str, Any]) -> Dict[str, Any]:
    """Build the payload of a ``legacy_event_id_assigned`` record.

    Args:
        ordinal: 1-based index of the legacy record among parsed records.
        record: The parsed legacy record the id is being assigned to.

    Returns:
        The payload dict. It carries the *full* digest as well as the derived
        id, so an auditor can re-verify the derivation without re-reading the
        line, and can tell a changed line from a changed recipe.

    Raises:
        ValueError: If ``ordinal`` is not a positive integer.
    """
    return {
        "ordinal": ordinal,
        "assigned_event_id": legacy_event_id(ordinal, record),
        "content_sha256": content_digest(record),
        "legacy_event_type": record.get("event_type"),
        "recipe_version": LEGACY_ID_RECIPE_VERSION,
    }


def scan_legacy_records(events: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return one summary row per repaired legacy record in ``events``.

    Operates on the output of `seldon.core.events.read_events`, i.e. on records
    that have *already* been normalised, so the id is read back rather than
    re-derived.

    Args:
        events: Records as returned by `read_events`.

    Returns:
        A list of ``{"ordinal", "event_id", "event_type"}`` dicts, in log order.
        Empty when the log has no legacy records.
    """
    rows: List[Dict[str, Any]] = []
    for ordinal, event in enumerate(events, start=1):
        if event.get("legacy") and is_legacy_event_id(event.get("event_id")):
            rows.append(
                {
                    "ordinal": ordinal,
                    "event_id": event["event_id"],
                    "event_type": event.get("event_type"),
                }
            )
    return rows


def assignment_records(events: Iterable[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """Index the ``legacy_event_id_assigned`` records already in a log.

    Args:
        events: Records as returned by `read_events`.

    Returns:
        Mapping of ordinal → assignment payload. A later record for the same
        ordinal replaces an earlier one, so a re-run of a corrected migration is
        the last word.
    """
    out: Dict[int, Dict[str, Any]] = {}
    for event in events:
        if event.get("event_type") != LEGACY_ASSIGNMENT_EVENT_TYPE:
            continue
        payload = event.get("payload") or {}
        ordinal = payload.get("ordinal")
        if isinstance(ordinal, int):
            out[ordinal] = payload
    return out


def verify_assignments(events: List[Dict[str, Any]]) -> List[str]:
    """Cross-check frozen assignment records against the live derivation.

    This is the tamper detector. Every ``legacy_event_id_assigned`` record froze
    an ordinal, a derived id and a content digest at migration time. If the
    legacy line at that ordinal still has the same content, re-deriving today
    reproduces both. A mismatch means the append-only log was edited.

    Args:
        events: Records as returned by `read_events`.

    Returns:
        A list of human-readable problem descriptions, empty when every
        assignment reconciles.
    """
    problems: List[str] = []
    assignments = assignment_records(events)
    if not assignments:
        return problems

    by_ordinal = {row["ordinal"]: row for row in scan_legacy_records(events)}

    for ordinal in sorted(assignments):
        payload = assignments[ordinal]
        recorded_id = payload.get("assigned_event_id")
        row = by_ordinal.get(ordinal)
        if row is None:
            problems.append(
                f"ordinal {ordinal}: an assignment record claims legacy id "
                f"{recorded_id!r}, but the record at that position is not legacy. "
                f"The event log was reordered or rewritten."
            )
            continue
        if row["event_id"] != recorded_id:
            problems.append(
                f"ordinal {ordinal}: recorded id {recorded_id!r} does not match "
                f"the id derived from the line today ({row['event_id']!r}). "
                f"The legacy line was edited after its id was assigned."
            )
    return problems


def unassigned_ordinals(events: List[Dict[str, Any]]) -> List[int]:
    """Return ordinals of legacy records that have no assignment record yet.

    Args:
        events: Records as returned by `read_events`.

    Returns:
        Ordinals in ascending order. Empty when the migration is complete (or
        when there are no legacy records at all).
    """
    assigned = set(assignment_records(events))
    return [row["ordinal"] for row in scan_legacy_records(events) if row["ordinal"] not in assigned]


def raw_records(path) -> List[Dict[str, Any]]:
    """Read a JSONL log into parsed records, preserving order.

    Used by the migration, which needs the *unnormalised* records: the id is
    derived from the line as written, so normalising first would hash the
    repaired shape instead.

    Skips blank and malformed lines, exactly as
    `seldon.core.events.read_events` does. That equivalence is the contract:
    the ordinal is the index among *parsed* records, so the migration and the
    reader must agree on which lines count. If one of them counted an
    unparseable line and the other did not, every subsequent ordinal — and
    therefore every derived id — would differ between them.

    Args:
        path: Path to the JSONL event log.

    Returns:
        The parsed records, in log order.

    Raises:
        OSError: If the file cannot be read.
    """
    from pathlib import Path as _Path

    p = _Path(path)
    if not p.exists():
        return []
    out: List[Dict[str, Any]] = []
    with open(p, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out
