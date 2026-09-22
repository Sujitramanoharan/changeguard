"""
ChangeGuard controlled agent pipeline.

Flow (perceive -> gather evidence via tools -> reason -> recommend):
  1. Retrieve similar past changes (FAISS)
  2. Derive backend historical context
  3. Predict risk with the ML model
  4. Gather incident / schedule / rollback evidence (tools)
  5. Calculate the authoritative deterministic risk policy
  6. Send evidence to Groq -> explanation only
"""

import truststore
truststore.inject_into_ssl()

import os
from pathlib import Path

from dotenv import load_dotenv

# Load Groq key from .env sitting in the project root
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

from predict import predict_risk
from retrieval import find_similar_changes
from tools import (
    get_incident_history,
    check_schedule_conflict,
    get_rollback_status,
)
from build_index import change_to_text
from context import derive_change_context
from risk_policy import calculate_risk_policy


def describe_document_evidence(change: dict) -> dict:
    """Summarize whether an uploaded rollback document backs up the claim."""

    provided = bool(change.get("rollback_document_provided"))
    verified = bool(change.get("rollback_document_verified"))
    claims_rollback = change.get("rollback_plan_exists") == "Yes"

    if provided and verified:
        note = (
            "A rollback plan document was uploaded and verified - it "
            "contains a real, numbered rollback procedure."
        )
    elif provided and not verified:
        note = (
            "CRITICAL: A rollback plan document was uploaded but does "
            "not substantiate a real rollback procedure - the claimed "
            "rollback plan is not backed by evidence."
        )
    elif claims_rollback:
        note = (
            "No supporting document was uploaded - the rollback plan "
            "is self-attested only."
        )
    else:
        note = "No rollback document evidence submitted."

    return {
        "provided": provided,
        "verified": verified,
        "note": note,
    }


def generate_fallback_assessment(
    change,
    ml,
    similar,
    incidents,
    schedule,
    rollback,
):
    """Fallback rule-grounded reasoning when LLM is unavailable."""

    policy = calculate_risk_policy(
        ml,
        change,
        similar,
        schedule,
    )

    rec = policy["recommendation"]
    level = policy["risk_level"]

    prob = ml.get("risk_probability", 0.3)
    failed_similar_count = policy["failed_similar_count"]
    has_rollback = policy["has_rollback"]
    tested_rollback = policy["tested_rollback"]
    has_conflict = policy["has_schedule_conflict"]

    justification_parts = []

    justification_parts.append(
        f"ML Model predicts a {round(prob * 100)}% failure risk "
        f"for {change.get('system', 'this system')}."
    )

    if len(similar) > 0:
        justification_parts.append(
            f"Historical analysis of {len(similar)} similar changes "
            f"showed {failed_similar_count} past failures or incidents."
        )

    if incidents.get("note"):
        justification_parts.append(
            incidents["note"]
        )

    if not has_rollback:
        justification_parts.append(
            "CRITICAL: No rollback plan is present for this change."
        )
    elif not tested_rollback:
        justification_parts.append(
            "Rollback plan is documented but has not been tested in staging."
        )

    if has_conflict:
        justification_parts.append(
            f"Scheduled during {change.get('requested_window', 'peak window')} "
            f"which carries higher incident correlation."
        )

    if policy.get("evidence_mismatch"):
        justification_parts.append(
            "CRITICAL: A rollback plan document was uploaded but does "
            "not substantiate a real rollback procedure."
        )

    justification = " ".join(justification_parts)

    return (
        f"RECOMMENDATION: {rec}\n"
        f"RISK LEVEL: {level}\n"
        f"JUSTIFICATION: {justification}"
    )


def assess_change(change: dict) -> dict:
    """Run the full ChangeGuard assessment on one change request."""

    # ---------------------------------------------------------
    # 1. Retrieve similar past changes
    # ---------------------------------------------------------

    query = change_to_text(
        {
            **change,
            "description": change.get("description", ""),
        }
    )

    similar = find_similar_changes(
        query,
        k=5,
    )

    # ---------------------------------------------------------
    # 2. Derive backend historical context
    # ---------------------------------------------------------

    historical_context = derive_change_context(
        change,
        similar_changes=similar,
    )

    # Add backend-derived historical features to a copy of
    # the current request before sending it to the ML model.
    enriched_change = {
        **change,
        **historical_context,
    }

    # ---------------------------------------------------------
    # 3. ML risk prediction
    # ---------------------------------------------------------

    ml = predict_risk(enriched_change)

    # ---------------------------------------------------------
    # 4. Gather tool evidence
    # ---------------------------------------------------------

    incidents = get_incident_history(
        change["system"]
    )

    schedule = check_schedule_conflict(
        change["requested_window"]
    )

    rollback = get_rollback_status(
        change["rollback_plan_exists"],
        change.get("rollback_plan_tested", "None"),
    )

    document = describe_document_evidence(change)

    # ---------------------------------------------------------
    # 5. Build evidence summary
    # ---------------------------------------------------------

    similar_txt = "\n".join(
        f"  - {s['change_id']}: "
        f"{s['change_type']} on {s['system']} "
        f"(similarity {s['similarity']}) "
        f"-> outcome: {s['outcome']}"
        for s in similar
    )

    evidence = f"""
CHANGE REQUEST:
  System: {change['system']}
  Type: {change['change_type']} | Size: {change['change_size']}
  Team: {change['requester_team']} | Window: {change['requested_window']}
  Rollback exists: {change['rollback_plan_exists']} | Tested: {change.get('rollback_plan_tested', 'None')}
  Schedule conflict: {change.get('schedule_conflict', 'No')}
  Description: {change.get('description', '(none)')}

BACKEND-DERIVED HISTORICAL CONTEXT:
  Similar past changes retrieved: {historical_context['similar_past_changes_count']}
  Similar past change failure rate: {historical_context['similar_past_changes_failure_rate']}
  Average system incidents in historical data: {historical_context['system_incidents_last_90_days']}

EVIDENCE GATHERED:
1. ML RISK MODEL:
   Probability of failure = {ml['risk_probability']}
   Model risk level = {ml['risk_level']}
   Flags risky = {ml['model_flags_risky']}

2. SIMILAR PAST CHANGES:
{similar_txt}

3. SYSTEM INCIDENT HISTORY:
   {incidents['note']}

4. SCHEDULE WINDOW:
   {schedule['note']}

5. ROLLBACK SAFETY:
   {rollback['note']}

6. ROLLBACK DOCUMENT VERIFICATION:
   {document['note']}
"""

    # ---------------------------------------------------------
    # 6. Authoritative deterministic risk policy
    # ---------------------------------------------------------

    policy = calculate_risk_policy(
        ml,
        change,
        similar,
        schedule,
    )

    # The deterministic policy is authoritative.
    # The LLM is NOT allowed to change the recommendation
    # or risk level.
    policy_recommendation = policy["recommendation"]
    policy_risk_level = policy["risk_level"]

    # ---------------------------------------------------------
    # 7. LLM explanation
    # ---------------------------------------------------------

    assessment_text = None

    if os.environ.get("GROQ_API_KEY"):
        try:
            from langchain_groq import ChatGroq

            _llm = ChatGroq(
                model="openai/gpt-oss-120b",
                temperature=0,
            )

            prompt = f"""You are ChangeGuard, an assistant to an IT Change Advisory Board.

Your role is to explain an already-determined risk decision.

The authoritative deterministic risk policy has already calculated:

RECOMMENDATION: {policy_recommendation}
RISK LEVEL: {policy_risk_level}

You MUST NOT change, override, reinterpret, or recalculate the recommendation or risk level.

Based ONLY on the evidence below, write a concise 2-4 sentence justification for the authoritative decision.

{evidence}

Your response MUST use this exact format:

JUSTIFICATION: <2-4 sentences using only facts supported by the evidence above.>
"""

            response = _llm.invoke(prompt)

            llm_justification = response.content.strip()

            # Groq may return the required JUSTIFICATION: prefix.
            # Remove only that prefix and preserve the explanation.
            if llm_justification.upper().startswith("JUSTIFICATION:"):
                llm_justification = llm_justification[
                    len("JUSTIFICATION:"):
                ].strip()

            # Safety check: if the LLM returns no usable explanation,
            # use the deterministic fallback explanation.
            if not llm_justification:
                raise ValueError(
                    "LLM returned an empty justification."
                )

            assessment_text = (
                f"RECOMMENDATION: {policy_recommendation}\n"
                f"RISK LEVEL: {policy_risk_level}\n"
                f"JUSTIFICATION: {llm_justification}"
            )


        except Exception as err:
            print(
                f"[ChangeGuard Agent Warning] "
                f"LLM invocation failed ({err}). "
                f"Using rule-grounded fallback."
            )

    # ---------------------------------------------------------
    # 8. Fallback if LLM is unavailable
    # ---------------------------------------------------------

    if not assessment_text:
        assessment_text = generate_fallback_assessment(
            change,
            ml,
            similar,
            incidents,
            schedule,
            rollback,
        )

    return {
        "ml_prediction": ml,
        "similar_changes": similar,
        "historical_context": historical_context,
        "enriched_change": enriched_change,
        "evidence": {
            "incidents": incidents,
            "schedule": schedule,
            "rollback": rollback,
            "document": document,
        },
        "policy": policy,
        "assessment": assessment_text,
    }


if __name__ == "__main__":
    test = {
        "system": "Payments-Service",
        "change_type": "Database-Schema-Change",
        "change_size": "Large",
        "requester_team": "Backend",
        "requested_window": "Peak-Hours",
        "rollback_plan_exists": "No",
        "rollback_plan_tested": "None",
        "schedule_conflict": "Yes",
        "description": (
            "Adding a new column to the payments "
            "transactions table."
        ),
    }

    result = assess_change(test)

    print("\n" + "=" * 60)
    print("ML PREDICTION:", result["ml_prediction"])
    print("=" * 60)
    print("HISTORICAL CONTEXT:", result["historical_context"])
    print("=" * 60)
    print("RISK POLICY:", result["policy"])
    print("=" * 60)
    print(result["assessment"])
    print("=" * 60)
