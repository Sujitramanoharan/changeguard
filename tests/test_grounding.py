"""Numbers in an LLM explanation must come from the evidence it was given."""

import agent
import agent_graph
import ticket_risk
from grounding import unsupported_numbers

EVIDENCE = """ML RISK MODEL (Rabobank change model):
   Predicted probability for THIS change = 0.0026 (0.26%)
   Average across all historical changes = 4.6%
   Relative risk = 0.06x a typical change
The affected system had 0 incident(s) in the last 30 days. Historically, 0.3% of
3,497 changes on 'Windows Server' systems were followed by more incidents."""


def test_numbers_quoted_from_the_evidence_pass():
    text = ("The model predicts a 0.26% probability (0.06x a typical change, average 4.6%); "
            "0.3% of 3,497 similar changes had incidents and none in the last 30 days.")
    assert unsupported_numbers(text, EVIDENCE) == []


def test_percent_and_fraction_forms_of_the_same_number_pass():
    assert unsupported_numbers("probability 0.003, about 0.26 %", EVIDENCE) == []
    assert unsupported_numbers("an average of 0.046", EVIDENCE) == []


def test_invented_numbers_are_caught():
    assert unsupported_numbers("The model gives a 12% chance of failure.", EVIDENCE) == ["12"]
    assert unsupported_numbers("probability 0.052", EVIDENCE) == ["0.052"]


def test_small_counts_are_always_allowed():
    assert unsupported_numbers("Two of 5 similar changes and 1 system.", EVIDENCE) == []


def test_agent_tool_labels_the_probability_and_hides_internal_numbers():
    ticket = agent.prepare_ticket({
        "ci_type": "computer", "ci_subtype": "Windows Server", "change_family": "Standard Change Type",
        "risk_classification": "Minor Change", "origin": "Problem", "incidents_30d": 0,
        "planned_start": "2026-10-06T10:00", "planned_hours": 2, "systems_affected": 4,
        "downtime": False, "emergency": False, "cab_required": False,
    })
    ml = ticket_risk.predict(ticket)
    agent_graph._CURRENT_TICKET.set(ticket)

    text = agent_graph.ml_risk_score.invoke({})

    assert "Predicted probability for THIS change" in text
    assert "Average across all historical changes" in text
    # The 0-1 risk index and raw base-rate decimal were the confusable numbers.
    assert str(ml["risk_index"]) not in text
    assert f"= {ml['base_rate']}" not in text


def test_explanation_with_an_unsupported_number_falls_back(monkeypatch):
    class Reply:
        content = "JUSTIFICATION: The model predicts a 7.5% failure probability for this change."

    class FakeGroq:
        def __init__(self, *a, **k):
            pass

        def invoke(self, prompt):
            return Reply()

    import langchain_groq
    monkeypatch.setattr(langchain_groq, "ChatGroq", FakeGroq)
    monkeypatch.setenv("GROQ_API_KEY", "test")

    text, source = agent.explain({"recommendation": "APPROVE", "risk_level": "Low"}, EVIDENCE)

    assert (text, source) == (None, "fallback")
