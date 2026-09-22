"""Deterministic verification that an uploaded rollback document is credible.

This is a structural/keyword heuristic, not an AI judgment call - it plays
the same role as the other evidence tools in tools.py (deterministic,
auditable), so the LLM still never decides anything. A document is
"verified" only if it is long enough, uses real rollback/recovery
terminology, and contains an actual numbered procedure - not just the
word "rollback" mentioned once in passing.
"""

import re


MIN_LENGTH = 120

ROLLBACK_KEYWORDS = [
    "rollback", "roll back", "revert", "restore", "recovery",
    "backup", "undo", "fallback", "restore point", "snapshot",
]

STEP_PATTERN = re.compile(r"(^|\n)\s*(step\s*\d+|\d+[.)])", re.IGNORECASE)


def verify_rollback_document(text: str) -> dict:
    """Score whether a document plausibly documents a real rollback procedure."""

    cleaned = (text or "").strip()
    length = len(cleaned)
    lower = cleaned.lower()

    matched_keywords = [kw for kw in ROLLBACK_KEYWORDS if kw in lower]
    has_steps = bool(STEP_PATTERN.search(cleaned))

    long_enough = length >= MIN_LENGTH
    has_keywords = len(matched_keywords) >= 2

    verified = long_enough and has_keywords and has_steps

    reasons = []

    if not long_enough:
        reasons.append(
            f"Document is only {length} characters - too short to "
            f"describe a real procedure."
        )

    if not has_keywords:
        reasons.append(
            "Document does not contain rollback/recovery terminology."
        )

    if not has_steps:
        reasons.append(
            "Document does not contain a numbered step-by-step procedure."
        )

    if verified:
        reasons.append(
            f"Found {len(matched_keywords)} rollback-related terms and "
            f"a numbered procedure."
        )

    return {
        "verified": verified,
        "length": length,
        "matched_keywords": matched_keywords,
        "has_numbered_steps": has_steps,
        "reasons": reasons,
    }
