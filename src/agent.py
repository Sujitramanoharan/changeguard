"""
ChangeGuard controlled agent pipeline.

Flow (perceive -> gather evidence via tools -> reason -> recommend):
  1. Predict risk with the ML model
  2. Retrieve similar past changes (FAISS)
  3. Gather incident / schedule / rollback evidence (tools)
  4. Send all evidence to Groq -> reasoned recommendation + justification
"""
import truststore
truststore.inject_into_ssl()
import os
import json
from pathlib import Path
from dotenv import load_dotenv
from langchain_groq import ChatGroq

from predict import predict_risk
from retrieval import find_similar_changes
from tools import get_incident_history, check_schedule_conflict, get_rollback_status
from build_index import change_to_text  # reuse the same text format

# Load Groq key from .env sitting in the project root
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

_llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0)


def assess_change(change: dict) -> dict:
    """Run the full ChangeGuard assessment on one change request."""

    # --- 1. ML risk prediction ---
    ml = predict_risk(change)

    # --- 2. Retrieve similar past changes ---
    query = change_to_text({**change, "description": change.get("description", "")})
    similar = find_similar_changes(query, k=5)

    # --- 3. Gather tool evidence ---
    incidents = get_incident_history(change["system"])
    schedule = check_schedule_conflict(change["requested_window"])
    rollback = get_rollback_status(
        change["rollback_plan_exists"], change.get("rollback_plan_tested", "None")
    )

    # --- 4. Build the evidence summary for the LLM ---
    similar_txt = "\n".join(
        f"  - {s['change_id']}: {s['change_type']} on {s['system']} "
        f"(similarity {s['similarity']}) -> outcome: {s['outcome']}"
        for s in similar
    )

    evidence = f"""
CHANGE REQUEST:
  System: {change['system']}
  Type: {change['change_type']} | Size: {change['change_size']}
  Team: {change['requester_team']} | Window: {change['requested_window']}
  Rollback exists: {change['rollback_plan_exists']} | Tested: {change.get('rollback_plan_tested','None')}
  Description: {change.get('description','(none)')}

EVIDENCE GATHERED:
1. ML RISK MODEL: probability of failure = {ml['risk_probability']}, level = {ml['risk_level']}, flags risky = {ml['model_flags_risky']}
2. SIMILAR PAST CHANGES:
{similar_txt}
3. SYSTEM INCIDENT HISTORY: {incidents['note']}
4. SCHEDULE WINDOW: {schedule['note']}
5. ROLLBACK SAFETY: {rollback['note']}
"""

    # --- 5. Ask Groq to reason over the evidence ---
    prompt = f"""You are ChangeGuard, an assistant to an IT Change Advisory Board.
Based ONLY on the evidence below, produce a risk assessment.

{evidence}

Respond in this exact format:
RECOMMENDATION: <APPROVE / REVIEW / REJECT>
RISK LEVEL: <Low / Medium / High>
JUSTIFICATION: <2-4 sentences. Reference the specific evidence above - the ML risk, the similar past changes and their outcomes, incident history, schedule, and rollback status. Do not invent facts not in the evidence.>
"""

    response = _llm.invoke(prompt)

    return {
        "ml_prediction": ml,
        "similar_changes": similar,
        "evidence": {
            "incidents": incidents,
            "schedule": schedule,
            "rollback": rollback,
        },
        "assessment": response.content,
    }


if __name__ == "__main__":
    test = {
        "system": "Payments-Service", "change_type": "Database-Schema-Change",
        "change_size": "Large", "requester_team": "Backend",
        "requested_window": "Peak-Hours", "rollback_plan_exists": "No",
        "rollback_plan_tested": "None", "similar_past_changes_count": 5,
        "similar_past_changes_failure_rate": 0.4,
        "system_incidents_last_90_days": 3, "schedule_conflict": "Yes",
        "description": "Adding a new column to the payments transactions table.",
    }
    result = assess_change(test)
    print("\n" + "="*60)
    print("ML PREDICTION:", result["ml_prediction"])
    print("="*60)
    print(result["assessment"])
    print("="*60)