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


def test_llm_justification_prefix_is_stripped_not_truncated(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr("langchain_groq.ChatGroq", FakeChatGroq)

    change = {
        "system": "Payments-Service",
        "change_type": "Deployment",
        "change_size": "Small",
        "requester_team": "Backend",
        "requested_window": "Off-Hours-Weekday",
        "rollback_plan_exists": "Yes",
        "rollback_plan_tested": "Yes",
        "schedule_conflict": "No",
        "description": "Routine deployment for regression test.",
    }

    result = agent.assess_change(change)

    assert "This change carries elevated risk" in result["assessment"]
    assert "because of the missing rollback plan" in result["assessment"]
