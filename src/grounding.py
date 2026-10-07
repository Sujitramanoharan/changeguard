"""Check that every number in an LLM explanation comes from the evidence.

The LLM only explains a decision the policy already made, but a CAB member
reads its numbers as facts. An earlier agent run quoted the historical
average (0.052) as the change's own probability (0.0026): a real number,
attached to the wrong thing. Clearer evidence (agent_graph.ml_risk_score)
fixes that cause; this check is the safety net for any number the model
invents or garbles.

A number in the explanation is supported when, at its own precision, it
equals a number in the evidence, or that number as a percentage (0.0026 ->
0.26%) or as a fraction (4.6% -> 0.046). Small counts (0-10) are always
allowed: "two of the factors", "1 system".

It cannot catch a supported number used for the wrong quantity - that is
what the labelled evidence is for.
"""

import re

NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*(?:\.\d+)?")

ALWAYS_OK = set(range(0, 11))


def _parse(token: str) -> tuple[float, int] | None:
    token = token.replace(",", "")
    try:
        value = float(token)
    except ValueError:
        return None
    decimals = len(token.split(".")[1]) if "." in token else 0
    return value, decimals


def numbers(text: str) -> list[tuple[str, float, int]]:
    out = []
    for match in NUMBER.finditer(text or ""):
        parsed = _parse(match.group())
        if parsed:
            out.append((match.group(), *parsed))
    return out


def unsupported_numbers(explanation: str, evidence: str) -> list[str]:
    """Numbers in the explanation that no evidence number accounts for."""

    known = []
    for _, value, _ in numbers(evidence):
        known += [value, value * 100, value / 100]

    missing = []
    for token, value, decimals in numbers(explanation):
        if decimals == 0 and value in ALWAYS_OK:
            continue
        tolerance = 0.5 * 10 ** -decimals + 1e-9
        if not any(abs(value - k) <= tolerance for k in known):
            missing.append(token)

    return missing
