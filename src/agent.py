"""
ChangeGuard controlled pipeline.

Two kinds of change, one decision process:

  Change ticket (ITIL)            Code change (GitHub commit / PR)
  - ticket model (Rabobank)       - code model (ApacheJIT)
  - similar real changes          - similar real commits
  - incident / window evidence    - diff evidence
            \\                      /
             rollback readiness + uploaded document check
                         |
          RedTeamGPT screens the free text (prompt_guard)
                         |
          deterministic risk policy (authoritative)
                         |
          LLM writes the explanation only (rule-based fallback)
"""

import truststore
truststore.inject_into_ssl()

import os
from datetime import datetime

import config  # noqa: F401  (loads .env, network settings)

import code_risk
import prompt_guard
import similarity
import ticket_risk
from config import CODE_INDEX_PATH, TICKET_INDEX_PATH
from risk_policy import calculate_risk_policy
from tools import (
    check_schedule_conflict,
    describe_code_change,
    get_incident_history,
    get_rollback_status,
)


LLM_MODEL = "openai/gpt-oss-120b"


# -------------------------------------------------------------------
# Shared evidence helpers
# -------------------------------------------------------------------

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


def describe_similar(similar: list) -> dict:
    bad = sum(1 for s in similar if s.get("bad"))
    return {
        "count": len(similar),
        "bad": bad,
        "note": (
            f"{bad} of the {len(similar)} most similar real historical "
            f"changes went wrong."
            if similar else "No similar historical changes found."
        ),
    }


def prepare_ticket(ticket: dict) -> dict:
    """Derive model inputs (start day/hour) from the planned start."""

    ticket = dict(ticket)
    start = ticket.get("planned_start")

    if start and (ticket.get("weekday") is None or ticket.get("hour") is None):
        when = datetime.fromisoformat(str(start))
        ticket["weekday"] = when.weekday()
        ticket["hour"] = when.hour

    for flag in ("downtime", "emergency", "cab_required"):
        ticket[flag] = int(bool(ticket.get(flag)))

    return ticket


# -------------------------------------------------------------------
# Explanation (LLM with rule-based fallback)
# -------------------------------------------------------------------

def fallback_justification(ml: dict, policy: dict, evidence: dict) -> str:
    """Rule-grounded explanation used when the LLM is unavailable."""

    parts = [
        f"The {'code' if ml.get('model') == 'code' else 'change'} risk model rates this change "
        f"{ml['relative_risk']}x as risky as a typical change "
        f"({ml['risk_probability'] * 100:.1f}% probability)."
    ]

    if ml.get("factors"):
        top = ml["factors"][0]
        parts.append(f"The biggest factor is {top['label'].lower()} ({top['value']}), which {top['direction']}.")

    parts.append(evidence["similar"]["note"])

    for key in ("incidents", "schedule", "diff"):
        if key in evidence:
            parts.append(evidence[key]["note"])

    if not policy["has_rollback"]:
        parts.append("CRITICAL: No rollback plan is present for this change.")
    elif not policy["tested_rollback"]:
        parts.append("The rollback plan has not been tested.")

    if policy.get("evidence_mismatch"):
        parts.append(
            "CRITICAL: A rollback plan document was uploaded but does "
            "not substantiate a real rollback procedure."
        )

    return " ".join(parts)


def explain(policy: dict, evidence_text: str, llm_allowed: bool = True) -> tuple[str | None, str]:
    """Ask the LLM to explain an already-made decision.

    Returns (justification or None, source).
    """

    if not llm_allowed or not os.environ.get("GROQ_API_KEY"):
        return None, "fallback"

    try:
        from langchain_groq import ChatGroq

        llm = ChatGroq(model=LLM_MODEL, temperature=0)

        prompt = f"""You are ChangeGuard, an assistant to an IT Change Advisory Board.

Your role is to explain an already-determined risk decision.

The authoritative deterministic risk policy has already calculated:

RECOMMENDATION: {policy['recommendation']}
RISK LEVEL: {policy['risk_level']}

You MUST NOT change, override, reinterpret, or recalculate the recommendation or risk level.

Based ONLY on the evidence below, write a concise 2-4 sentence justification for the authoritative decision.

{evidence_text}

Your response MUST use this exact format:

JUSTIFICATION: <2-4 sentences using only facts supported by the evidence above.>
"""

        text = llm.invoke(prompt).content.strip()

        # Remove the required prefix and keep the explanation.
        if text.upper().startswith("JUSTIFICATION:"):
            text = text[len("JUSTIFICATION:"):].strip()

        if not text:
            raise ValueError("LLM returned an empty justification.")

        return text, "llm"

    except Exception as err:
        print(
            f"[ChangeGuard Agent Warning] LLM invocation failed ({err}). "
            f"Using rule-grounded fallback."
        )
        return None, "fallback"


def evidence_text(header: str, ml: dict, similar: list, evidence: dict) -> str:
    factors = "\n".join(
        f"   - {f['label']} = {f['value']} ({f['direction']})"
        for f in ml.get("factors", [])
    )
    sims = "\n".join(
        f"   - {s['change_id']} ({s['system']}, {s.get('date', '')}): {s['outcome']}"
        for s in similar
    )
    notes = "\n".join(
        f"{i}. {key.upper()}: {value['note']}"
        for i, (key, value) in enumerate(evidence.items(), start=4)
    )

    return f"""{header}

EVIDENCE GATHERED:
1. ML RISK MODEL ({'ApacheJIT code model' if ml['model'] == 'code' else 'Rabobank change model'}):
   Probability = {ml['risk_probability']} ({ml['relative_risk']}x the average change)
   Model risk level = {ml['risk_level']}

2. TOP FACTORS (SHAP):
{factors}

3. MOST SIMILAR REAL HISTORICAL CHANGES:
{sims}

{notes}
"""


def screen_free_text(fields: dict, change: dict, evidence: dict) -> dict:
    """Run RedTeamGPT over the user-written fields and record the result."""

    guard = prompt_guard.screen(fields)
    change["prompt_injection_flagged"] = prompt_guard.is_flagged(guard)

    if guard["status"] != "not_configured":
        evidence["security"] = {"status": guard["status"], "note": guard["note"]}

    return guard


def finish(kind: str, change: dict, ml: dict, similar: list,
           evidence: dict, schedule: dict, header: str, guard: dict) -> dict:
    """Apply the policy, explain it, and package the result."""

    policy = calculate_risk_policy(ml, change, similar, schedule)

    justification, source = explain(
        policy,
        evidence_text(header, ml, similar, evidence),
        llm_allowed=prompt_guard.llm_allowed(guard),
    )

    if not justification:
        justification = fallback_justification(ml, policy, evidence)

    return {
        "kind": kind,
        "ml_prediction": ml,
        "similar_changes": similar,
        "evidence": evidence,
        "policy": policy,
        "explanation_source": source,
        "prompt_guard": guard,
        "assessment": (
            f"RECOMMENDATION: {policy['recommendation']}\n"
            f"RISK LEVEL: {policy['risk_level']}\n"
            f"JUSTIFICATION: {justification}"
        ),
    }


# -------------------------------------------------------------------
# Change ticket (ITIL) assessment
# -------------------------------------------------------------------

def similar_tickets(ticket: dict) -> list:
    b = ticket_risk.load()
    frame = ticket_risk.to_frame(ticket, b)[ticket_risk.FEATURES]
    return similarity.search(TICKET_INDEX_PATH, b["encoder"], b["meta"], frame)


def assess_ticket(ticket: dict) -> dict:
    """Run the full ChangeGuard assessment on one change ticket."""

    ticket = prepare_ticket(ticket)

    ml = ticket_risk.predict(ticket)
    similar = similar_tickets(ticket)
    incidents = get_incident_history(ticket)
    schedule = check_schedule_conflict(ticket)

    evidence = {
        "similar": describe_similar(similar),
        "incidents": incidents,
        "schedule": schedule,
        "rollback": get_rollback_status(
            ticket["rollback_plan_exists"],
            ticket.get("rollback_plan_tested", "None"),
        ),
        "document": describe_document_evidence(ticket),
    }

    guard = screen_free_text(
        {"title": ticket.get("title"), "description": ticket.get("description")}, ticket, evidence
    )
    title = prompt_guard.safe_text("title", ticket.get("title", "(untitled)"), guard)
    description = prompt_guard.safe_text("description", ticket.get("description") or "(none)", guard)

    header = f"""CHANGE TICKET:
  Title: {title}
  System: {ticket.get('ci_subtype')} ({ticket.get('ci_type')}) | Change type: {ticket.get('change_family')}
  Risk classification: {ticket.get('risk_classification')} | Emergency: {'Yes' if ticket['emergency'] else 'No'}
  Planned: {ticket.get('planned_hours')} h, {ticket.get('systems_affected')} system(s) affected
  Rollback exists: {ticket['rollback_plan_exists']} | Tested: {ticket.get('rollback_plan_tested', 'None')}
  Schedule conflict reported: {ticket.get('schedule_conflict', 'No')}
  Description: {description}"""

    return finish("ticket", ticket, ml, similar, evidence, schedule, header, guard)


# -------------------------------------------------------------------
# Code change (GitHub) assessment
# -------------------------------------------------------------------

def similar_commits(metrics: dict) -> list:
    b = code_risk.load()
    return similarity.search(
        CODE_INDEX_PATH, b["encoder"], b["meta"], code_risk.to_frame(metrics)
    )


def code_rollback_readiness(analysis: dict) -> tuple[str, str, str]:
    """Rollback readiness of a code change: (exists, tested, note).

    Any commit can be rolled back with `git revert`, so the real risks
    are schema migrations without a reverse path (data changes cannot be
    reverted by reverting code) and changes shipped without tests.
    """

    details = analysis.get("analysis", {})
    tested = "Yes" if details.get("touches_tests") else "No"
    is_migration = analysis.get("change_type") == "Database-Schema-Change"
    has_reverse = bool(details.get("detected_rollback_language"))

    if is_migration and not has_reverse:
        return (
            "No",
            "None",
            "Touches database migrations/schema with no reverse migration "
            "or rollback path in the diff - reverting the code will not "
            "undo the data change.",
        )

    note = (
        "Schema change includes a reverse migration / rollback path."
        if is_migration
        else "Code-only change - it can be rolled back by reverting the commit."
    )
    note += (
        " Test files were updated alongside the change."
        if tested == "Yes"
        else " No test files were changed, so the change is not verified by tests."
    )

    return "Yes", tested, note


def assess_code(analysis: dict, context: dict | None = None) -> dict:
    """Assess a real GitHub commit / PR analysed by repo_change_analysis.

    context: optional reviewer-supplied deployment details
    (schedule_conflict, rollback document evidence).
    """

    context = context or {}
    metrics = analysis["code_metrics"]
    details = analysis.get("analysis", {})

    rollback_exists, rollback_tested, rollback_note = code_rollback_readiness(analysis)

    change = {
        "title": analysis["description"],
        "system": analysis["system"],
        "rollback_plan_exists": rollback_exists,
        "rollback_plan_tested": rollback_tested,
        "schedule_conflict": context.get("schedule_conflict", "No"),
        "rollback_document_provided": context.get("rollback_document_provided", False),
        "rollback_document_verified": context.get("rollback_document_verified", False),
    }

    ml = code_risk.predict(metrics)
    similar = similar_commits(metrics)

    evidence = {
        "similar": describe_similar(similar),
        "diff": describe_code_change(
            {"change_type": analysis.get("change_type"), **details}, metrics
        ),
        "rollback": {
            "rollback_exists": rollback_exists,
            "rollback_tested": rollback_tested,
            "note": rollback_note,
        },
        "document": describe_document_evidence(change),
    }

    # Screen the whole stored message (title and body): only its first line
    # reaches the LLM, but a manipulation attempt anywhere in it matters to the CAB.
    guard = screen_free_text(
        {"message": details.get("commit_message") or analysis["description"]}, change, evidence
    )
    message = prompt_guard.safe_text("message", analysis["description"], guard)

    header = f"""CODE CHANGE:
  Repository: {analysis['system']}
  {message}
  Author: {details.get('author', 'unknown')} | Files: {metrics['nf']} | +{metrics['la']}/-{metrics['ld']} lines
  Rollback evidence in diff: {analysis['rollback_plan_exists']} | Tests changed: {'Yes' if details.get('touches_tests') else 'No'}"""

    result = finish("code", change, ml, similar, evidence, {}, header, guard)
    result["code_metrics"] = metrics
    result["analysis"] = details
    result["change"] = change

    return result
