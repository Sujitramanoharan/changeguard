"""Regression test for the LLM justification prefix-stripping logic.

A prior bug indexed a single character (`text[len(prefix)]`) instead of
slicing the prefix off (`text[len(prefix):]`), which silently discarded
almost the entire LLM-generated explanation on every real call and made
the pipeline always fall back to the rule-based justification instead.
"""

import agent


class FakeResponse:
    def __init__(self, content):
        self.content = content


class FakeChatGroq:
    def __init__(self, *args, **kwargs):
        pass

    def invoke(self, prompt):
        return FakeResponse(
            "JUSTIFICATION: This change carries elevated risk because of "
            "the missing rollback plan and peak-hour timing."
        )


TICKET = {
    "title": "Regression test change",
    "ci_type": "computer",
    "ci_subtype": "Windows Server",
    "change_family": "Standard Change Type",
    "risk_classification": "Minor Change",
    "origin": "Problem",
    "incidents_30d": 0,
    "planned_start": "2026-10-06T10:00",
    "planned_hours": 2,
    "systems_affected": 1,
    "downtime": False,
    "emergency": False,
    "cab_required": False,
    "rollback_plan_exists": "Yes",
    "rollback_plan_tested": "Yes",
    "schedule_conflict": "No",
    "description": "Routine patch for regression test.",
}


def test_llm_justification_prefix_is_stripped_not_truncated(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr("langchain_groq.ChatGroq", FakeChatGroq)

    result = agent.assess_ticket(TICKET)

    assert result["explanation_source"] == "llm"
    assert "This change carries elevated risk" in result["assessment"]
    assert "because of the missing rollback plan" in result["assessment"]


def test_missing_llm_key_uses_rule_based_fallback(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    result = agent.assess_ticket(TICKET)

    assert result["explanation_source"] == "fallback"
    assert "as risky as a typical change" in result["assessment"]
