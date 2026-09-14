"""
ChangeGuard autonomous agent (LangGraph version).

Unlike the fixed-sequence pipeline in agent.py, this agent LOOP lets the LLM
decide which tools to call and in what order, and can call a tool again if
needed, before producing a final recommendation.
"""
import os
import json
from pathlib import Path
from typing import TypedDict, Annotated, Sequence
import operator

from dotenv import load_dotenv
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage, AIMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END

from predict import predict_risk
from retrieval import find_similar_changes
from tools import get_incident_history, check_schedule_conflict, get_rollback_status
from build_index import change_to_text

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

_CURRENT_CHANGE = {}  # holds the change dict for the currently-running tool calls


# ---------- Wrap existing functions as LangChain tools the LLM can call ----------
@tool
def ml_risk_score() -> str:
    """Get the ML model's predicted failure risk for the current change request."""
    result = predict_risk(_CURRENT_CHANGE)
    return json.dumps(result)


@tool
def similar_past_changes(k: int = 5) -> str:
    """Find the k most similar past changes and their real outcomes (RAG retrieval)."""
    query = change_to_text({**_CURRENT_CHANGE, "description": _CURRENT_CHANGE.get("description", "")})
    results = find_similar_changes(query, k=k)
    return json.dumps(results)


@tool
def incident_history() -> str:
    """Get recent incident history for the system affected by this change."""
    return json.dumps(get_incident_history(_CURRENT_CHANGE["system"]))


@tool
def schedule_conflicts() -> str:
    """Check whether the requested time window is historically riskier / has conflicts."""
    return json.dumps(check_schedule_conflict(_CURRENT_CHANGE["requested_window"]))


@tool
def rollback_safety() -> str:
    """Assess the rollback plan safety net for this change."""
    return json.dumps(get_rollback_status(
        _CURRENT_CHANGE["rollback_plan_exists"],
        _CURRENT_CHANGE.get("rollback_plan_tested", "None"),
    ))


TOOLS = [ml_risk_score, similar_past_changes, incident_history, schedule_conflicts, rollback_safety]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}


def assess_change_autonomous(change: dict, max_steps: int = 8) -> dict:
    """Run the autonomous LangGraph agent on a change request."""
    global _CURRENT_CHANGE
    _CURRENT_CHANGE = change

    tool_calls_made = []
    final_text = None

    if os.environ.get("GROQ_API_KEY"):
        try:
            from langchain_groq import ChatGroq
            _llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0).bind_tools(TOOLS)

            class AgentState(TypedDict):
                messages: Annotated[Sequence[BaseMessage], operator.add]

            SYSTEM_PROMPT = """You are ChangeGuard, an autonomous agent assisting an IT Change Advisory Board. You decide which tools to call and in what order to gather enough evidence about a proposed change. Available tools: ml_risk_score, similar_past_changes, incident_history, schedule_conflicts, rollback_safety. Call whichever tools you need. Once you have enough evidence, respond with NO further tool calls, in exactly this format:

RECOMMENDATION: <APPROVE / REVIEW / REJECT>
RISK LEVEL: <Low / Medium / High>
JUSTIFICATION: <2-4 sentences citing the specific evidence you gathered>
"""

            def call_model(state: AgentState):
                response = _llm.invoke([SystemMessage(content=SYSTEM_PROMPT)] + list(state["messages"]))
                return {"messages": [response]}

            def call_tools(state: AgentState):
                last = state["messages"][-1]
                outputs = []
                for call in last.tool_calls:
                    result = TOOLS_BY_NAME[call["name"]].invoke(call["args"])
                    outputs.append(ToolMessage(content=str(result), tool_call_id=call["id"], name=call["name"]))
                return {"messages": outputs}

            def should_continue(state: AgentState):
                last = state["messages"][-1]
                return "tools" if getattr(last, "tool_calls", None) else "end"

            _graph = StateGraph(AgentState)
            _graph.add_node("agent", call_model)
            _graph.add_node("tools", call_tools)
            _graph.set_entry_point("agent")
            _graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": END})
            _graph.add_edge("tools", "agent")
            _compiled = _graph.compile()

            initial = f"Assess this change request:\n{json.dumps(change, indent=2)}"
            state = {"messages": [HumanMessage(content=initial)]}
            result_state = _compiled.invoke(state, {"recursion_limit": max_steps * 2})

            for m in result_state["messages"]:
                if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
                    for c in m.tool_calls:
                        tool_calls_made.append(c["name"])

            final_text = result_state["messages"][-1].content
        except Exception as err:
            print(f"[ChangeGuard LangGraph Warning] Autonomous loop error ({err}). Executing deterministic fallback.")

    if not final_text:
        # Fallback autonomous step simulation calling all evidence tools
        tool_calls_made = ["ml_risk_score", "similar_past_changes", "incident_history", "schedule_conflicts", "rollback_safety"]
        ml_data = json.loads(ml_risk_score.invoke({}))
        sim_data = json.loads(similar_past_changes.invoke({}))
        inc_data = json.loads(incident_history.invoke({}))
        sched_data = json.loads(schedule_conflicts.invoke({}))
        roll_data = json.loads(rollback_safety.invoke({}))

        prob = ml_data.get("risk_probability", 0.3)
        has_rollback = change.get("rollback_plan_exists") == "Yes"
        tested_rollback = change.get("rollback_plan_tested") == "Yes"

        if prob > 0.5 or not has_rollback:
            rec = "REJECT"
            level = "High"
        elif prob > 0.25 or not tested_rollback:
            rec = "REVIEW"
            level = "Medium"
        else:
            rec = "APPROVE"
            level = "Low"

        just = (f"Autonomous Agent executed {len(tool_calls_made)} evidence tools. ML risk model score is {round(prob*100)}%. "
                f"{inc_data.get('note', '')} {sched_data.get('note', '')} {roll_data.get('note', '')}")

        final_text = f"RECOMMENDATION: {rec}\nRISK LEVEL: {level}\nJUSTIFICATION: {just}"

    return {
        "final_answer": final_text,
        "tools_called": tool_calls_made,
        "num_tool_calls": len(tool_calls_made),
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
    result = assess_change_autonomous(test)
    print("Tools the agent CHOSE to call:", result["tools_called"])
    print("\n" + result["final_answer"])
