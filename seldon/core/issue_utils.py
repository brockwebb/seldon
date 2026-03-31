"""Issue artifact utilities — enum validation and Eisenhower quadrant computation."""

from __future__ import annotations


ISSUE_ENUMS = {
    "issue_type": [
        "factual_error", "citation_gap", "unsupported_claim",
        "terminology_inconsistency", "internal_contradiction",
        "missing_content", "stale_content", "structural_flow",
        "style_formatting",
    ],
    "importance": ["high", "medium", "low"],
    "urgency": ["high", "medium", "low"],
    "detection_method": ["automated_check", "audit", "incidental", "build_failure"],
    "target": ["content", "citation", "terminology", "data", "structure"],
}


EISENHOWER_LABELS = {
    ("high", "high"): "DO NOW",
    ("high", "medium"): "DO SOON",
    ("high", "low"): "SCHEDULE",
    ("medium", "high"): "ACT SOON",
    ("medium", "medium"): "PLAN",
    ("medium", "low"): "BACKLOG",
    ("low", "high"): "BATCH",
    ("low", "medium"): "DEFER",
    ("low", "low"): "ELIMINATE",
}


def eisenhower_quadrant(importance: str, urgency: str) -> str:
    """Compute the Eisenhower quadrant label from importance and urgency axes."""
    return EISENHOWER_LABELS.get((importance, urgency), "UNKNOWN")


def validate_issue_enum(field: str, value: str) -> None:
    """Validate that a value is allowed for the given Issue enum field.

    Raises ValueError with allowed values listed if invalid.
    """
    allowed = ISSUE_ENUMS.get(field)
    if allowed is None:
        raise ValueError(f"Unknown Issue enum field: {field!r}")
    if value not in allowed:
        raise ValueError(
            f"Invalid {field}: {value!r}. Allowed: {', '.join(allowed)}"
        )
