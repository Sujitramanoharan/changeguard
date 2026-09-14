"""
ChangeGuard controlled agent pipeline.

Flow (perceive -> gather evidence via tools -> reason -> recommend):
  1. Predict risk with the ML model
  2. Retrieve similar past changes (FAISS)
  3. Gather incident / schedule / rollback evidence (tools)
  4. Send all evidence to Groq -> reasoned recommendation + justification (with fallback)
"""
import truststore
truststore.inject_into_ssl()
import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Load Groq key from .env sitting in the project root
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

from predict import predict_risk
from retrieval import find_similar_changes
from tools import get_incident_history, check_schedule_conflict, get_rollback_status
from build_index import change_to_text  # reuse the same text format


def generate_fallback_assessment(change, ml, similar, incidents, schedule, rollback):
    """Fallback rule-grounded reasoning when LLM key is absent or API is unreachable."""
    prob = ml.get("risk_probability", 0.3)
    failed_similar = [s for s in similar if s.get("outcome") in ["Failed", "Caused-Incident"]]
    has_rollback = change.get("rollback_plan_exists") == "Yes"
    tested_rollback = change.get("rollback_plan_tested") == "Yes"
    has_conflict = change.get("schedule_conflict") == "Yes" or schedule.get("conflict_frequency", 0) > 0.3
    
    # Calculate composite score
    score = prob * 0.4
    if not has_rollback:
        score += 0.25
    elif not tested_rollback:
        score += 0.1
    if has_conflict:
        score += 0.2
    if len(failed_similar) > 0:
        score += 0.15

    if score >= 0.55:
        rec = "REJECT"
        level = "High"
    elif score >= 0.30:
        rec = "REVIEW"
        level = "Medium"
    else:
        rec = "APPROVE"
        level = "Low"

    justification_parts = []
    justification_parts.append(f"ML Model predicts a {round(prob * 100)}% failure risk for {change.get('system', 'this system')}.")
    
    if len(similar) > 0:
        justification_parts.append(f"Historical analysis of {len(similar)} similar changes showed {len(failed_similar)} past failures or incidents.")
    
    if incidents.get("note"):
        justification_parts.append(incidents["note"])
        
    if not has_rollback:
        justification_parts.append("CRITICAL: No rollback plan is present for this change.")
    elif not tested_rollback:
        justification_parts.append("Rollback plan is documented but has not been tested in staging.")

    if has_conflict:
        justification_parts.append(f"Scheduled during {change.get('requested_window', 'peak window')} which carries higher incident correlation.")

    justification = " ".join(justification_parts)

    return f"""RECOMMENDATION: {rec}
RISK LEVEL: {level}
JUSTIFICATION: {justification}"""


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

    assessment_text = None
    if os.environ.get("GROQ_API_KEY"):
        try:
            from langchain_groq import ChatGroq
            _llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0)
            prompt = f"""You are ChangeGuard, an assistant to an IT Change Advisory Board.
Based ONLY on the evidence below, produce a risk assessment.

{evidence}

Respond in this exact format:
RECOMMENDATION: <APPROVE / REVIEW / REJECT>
RISK LEVEL: <Low / Medium / High>
JUSTIFICATION: <2-4 sentences. Reference the specific evidence above - the ML risk, the similar past changes and their outcomes, incident history, schedule, and rollback status. Do not invent facts not in the evidence.>
"""
            response = _llm.invoke(prompt)
            assessment_text = response.content
        except Exception as err:
            print(f"[ChangeGuard Agent Warning] LLM invocation failed ({err}). Using rule-grounded fallback.")

    if not assessment_text:
        assessment_text = generate_fallback_assessment(change, ml, similar, incidents, schedule, rollback)

    return {
        "ml_prediction": ml,
        "similar_changes": similar,
        "evidence": {
            "incidents": incidents,
            "schedule": schedule,
            "rollback": rollback,
        },
        "assessment": assessment_text,
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