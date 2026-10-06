"""
ChangeGuard autonomous agent (LangGraph version).

Unlike the fixed-sequence pipeline in agent.py, this agent LOOP lets the
LLM decide which evidence tools to call, and in what order, before it
writes its justification. The recommendation and risk level still come
from the shared deterministic risk policy - the agent can only explain.
"""

import json
import operator
import os
from contextvars import ContextVar
from typing import Annotated, Sequence, TypedDict

import truststore

truststore.inject_into_ssl()

import config  # noqa: F401  (loads .env, network settings)

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import tool
from langgraph.graph import END, StateGraph

import prompt_guard
import ticket_risk
from agent import (
    LLM_MODEL,
    describe_document_evidence,
    describe_similar,
    fallback_justification,
    prepare_ticket,
    similar_tickets,
)
from risk_policy import calculate_risk_policy
from tools import check_schedule_conflict, get_incident_history, get_rollback_status


# Each request gets its own ticket, so concurrent assessments never mix.
_CURRENT_TICKET: ContextVar[dict | None] = ContextVar(
    "changeguard_current_ticket",
    default=None,
)


def _ticket() -> dict:
    ticket = _CURRENT_TICKET.get()

    if ticket is None:
        raise RuntimeError("No active ChangeGuard request context.")

    return ticket


SYSTEM_PROMPT = """
You are ChangeGuard, an autonomous agent assisting an IT Change Advisory Board.

Gather evidence about the proposed change with the available tools:
- ml_risk_score: the risk model trained on real Rabobank change records
- similar_past_changes: the most similar real historical changes and outcomes
- incident_history: recent incidents on the affected system
- schedule_conflicts: historical risk of the planned start day/hour
- rollback_safety: rollback readiness

EVIDENCE RULES:
1. You MUST call ml_risk_score.
2. Call the tool that supports any fact before you state it.
3. Never invent evidence that no tool returned.
4. When you have enough evidence, stop calling tools.
"""


@tool
def ml_risk_score() -> str:
    """Risk model prediction for the current change, with its top factors."""

    return json.dumps(ticket_risk.predict(_ticket()))


@tool
def similar_past_changes() -> str:
    """The most similar real historical changes and what happened after them."""

    return json.dumps(similar_tickets(_ticket()))


@tool
def incident_history() -> str:
    """Recent incidents on the affected system and history for this system type."""

    return json.dumps(get_incident_history(_ticket()))


@tool
def schedule_conflicts() -> str:
    """Historical risk of changes started at the planned day and hour."""

    return json.dumps(check_schedule_conflict(_ticket()))


@tool
def rollback_safety() -> str:
    """Rollback readiness for the current change."""

    t = _ticket()
    return json.dumps(
        get_rollback_status(t["rollback_plan_exists"], t.get("rollback_plan_tested", "None"))
    )


TOOLS = [ml_risk_score, similar_past_changes, incident_history, schedule_conflicts, rollback_safety]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]


def run_agent_loop(ticket: dict, policy: dict, max_steps: int, guard: dict | None = None) -> tuple[str | None, list]:
    """Let the LLM choose tools and write a justification.

    Returns (justification or None, tools actually called).
    """

    from langchain_groq import ChatGroq

    prompt = SYSTEM_PROMPT + f"""

The authoritative ChangeGuard risk policy has already decided:

RECOMMENDATION: {policy['recommendation']}
RISK LEVEL: {policy['risk_level']}

You MUST NOT change these values. Gather evidence, then reply ONLY with:

JUSTIFICATION: <2-4 sentences using only evidence you actually gathered>
"""

    llm = ChatGroq(model=LLM_MODEL, temperature=0).bind_tools(TOOLS)

    def call_model(state: AgentState):
        return {"messages": [llm.invoke([SystemMessage(content=prompt)] + list(state["messages"]))]}

    def call_tools(state: AgentState):
        outputs = []

        for call in state["messages"][-1].tool_calls:
            if call["name"] not in TOOLS_BY_NAME:
                raise ValueError(f"Unknown tool requested: {call['name']}")

            outputs.append(ToolMessage(
                content=str(TOOLS_BY_NAME[call["name"]].invoke(call["args"])),
                tool_call_id=call["id"],
                name=call["name"],
            ))

        return {"messages": outputs}

    def should_continue(state: AgentState):
        return "tools" if getattr(state["messages"][-1], "tool_calls", None) else "end"

    graph = StateGraph(AgentState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", call_tools)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": END})
    graph.add_edge("tools", "agent")

    public = {k: v for k, v in ticket.items() if k not in ("weekday", "hour")}
    for field in ("title", "description"):
        if field in public:
            public[field] = prompt_guard.safe_text(field, public[field], guard or {})

    result = graph.compile().invoke(
        {"messages": [HumanMessage(content="Assess this change ticket:\n" + json.dumps(public, indent=2, default=str))]},
        {"recursion_limit": max_steps * 2},
    )

    called = [
        call["name"]
        for m in result["messages"]
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None)
        for call in m.tool_calls
    ]

    text = result["messages"][-1].content
    if not isinstance(text, str):
        return None, called

    text = text.strip()
    if text.upper().startswith("JUSTIFICATION:"):
        text = text[len("JUSTIFICATION:"):].strip()

    return (text or None), called


def assess_change_autonomous(ticket: dict, max_steps: int = 8) -> dict:
    """Autonomous assessment of a change ticket."""

    ticket = prepare_ticket(ticket)
    guard = prompt_guard.screen({"title": ticket.get("title"), "description": ticket.get("description")})
    ticket["prompt_injection_flagged"] = prompt_guard.is_flagged(guard)
    _CURRENT_TICKET.set(ticket)

    # Authoritative evidence for the policy - computed deterministically,
    # whatever the agent later decides to look at.
    ml = ticket_risk.predict(ticket)
    similar = similar_tickets(ticket)
    schedule = check_schedule_conflict(ticket)
    policy = calculate_risk_policy(ml, ticket, similar, schedule)

    justification, tools_called = None, []

    if os.environ.get("GROQ_API_KEY") and prompt_guard.llm_allowed(guard):
        try:
            justification, tools_called = run_agent_loop(ticket, policy, max_steps, guard)
        except Exception as err:
            print(f"[ChangeGuard LangGraph Warning] Autonomous loop error ({err}). Using fallback.")

    source = "llm" if justification else "fallback"

    evidence = {
        "similar": describe_similar(similar),
        "incidents": get_incident_history(ticket),
        "schedule": schedule,
        "rollback": get_rollback_status(
            ticket["rollback_plan_exists"], ticket.get("rollback_plan_tested", "None")
        ),
        "document": describe_document_evidence(ticket),
    }
    if guard["status"] != "not_configured":
        evidence["security"] = {"status": guard["status"], "note": guard["note"]}

    if not justification:
        # tools_called stays as recorded: the fallback gathers evidence
        # directly and must not be reported as agent tool calls.
        justification = fallback_justification(ml, policy, evidence)

    return {
        "kind": "ticket",
        "final_answer": (
            f"RECOMMENDATION: {policy['recommendation']}\n"
            f"RISK LEVEL: {policy['risk_level']}\n"
            f"JUSTIFICATION: {justification}"
        ),
        "tools_called": tools_called,
        "num_tool_calls": len(tools_called),
        "ml_prediction": ml,
        "similar_changes": similar,
        "evidence": evidence,
        "schedule": schedule,
        "policy": policy,
        "explanation_source": source,
        "prompt_guard": guard,
    }
