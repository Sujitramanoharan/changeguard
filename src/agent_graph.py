"""
ChangeGuard autonomous agent (LangGraph version).

Unlike the fixed-sequence pipeline in agent.py, this agent LOOP lets the LLM
decide which tools to call and in what order, and can call a tool again if
needed, before producing a final recommendation.

Phase 2:
- The client provides only current change-request fields.
- Historical ML features are derived by the backend.
- The ML model receives the complete 11-feature enriched change.
"""

import os
import json
import operator
from pathlib import Path
from typing import TypedDict, Annotated, Sequence
from contextvars import ContextVar

import truststore

truststore.inject_into_ssl()

from dotenv import load_dotenv
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    AIMessage,
)
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END

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


# -------------------------------------------------------------------
# Environment
# -------------------------------------------------------------------

load_dotenv(
    dotenv_path=Path(__file__).parent.parent / ".env"
)


# -------------------------------------------------------------------
# Request-scoped current change
# -------------------------------------------------------------------
# ContextVar gives each request/execution its own change context.
# This prevents concurrent autonomous assessments from overwriting
# each other's change data.

_CURRENT_CHANGE: ContextVar[dict | None] = ContextVar(
    "changeguard_current_change",
    default=None,
)


def _get_current_change() -> dict:
    """Return the current request's change data."""

    change = _CURRENT_CHANGE.get()

    if change is None:
        raise RuntimeError(
            "No active ChangeGuard request context."
        )

    return change


# -------------------------------------------------------------------
# System prompt
# -------------------------------------------------------------------

SYSTEM_PROMPT = """
You are ChangeGuard, an autonomous agent assisting an IT Change Advisory Board.

Your job is to gather evidence about the proposed change before producing a
final assessment.

Available evidence tools:
- ml_risk_score
- similar_past_changes
- incident_history
- schedule_conflicts
- rollback_safety

IMPORTANT EVIDENCE RULES:

1. You MUST call ml_risk_score.

2. You MUST call similar_past_changes before making any statement about
   similar historical changes, their outcomes, or their failure rate.

3. You MUST call incident_history before making any statement about incidents
   or historical failure rate for the affected system.

4. You MUST call schedule_conflicts before making any statement about schedule
   conflicts or historical risk of the requested window.

5. You MUST call rollback_safety before making any statement about rollback
   readiness or rollback safety.

6. Do NOT invent, assume, or infer evidence that was not returned by a tool.

7. The final justification may ONLY contain facts supported by:
   - the original change request, or
   - evidence returned by tools that you actually called.

8. If evidence is needed but has not been gathered, call the appropriate tool
   first.

9. You may decide which additional tools are necessary, but gather all
   evidence required to support every factual claim in your final
   justification.

10. Once enough evidence has been gathered, make NO further tool calls and
    respond exactly in this format:

RECOMMENDATION: <APPROVE / REVIEW / REJECT>
RISK LEVEL: <Low / Medium / High>
JUSTIFICATION: <2-4 sentences citing only evidence actually gathered>
"""


# -------------------------------------------------------------------
# LangGraph state
# -------------------------------------------------------------------

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]


# -------------------------------------------------------------------
# LangChain tools
# -------------------------------------------------------------------

@tool
def ml_risk_score() -> str:
    """Get the ML model's predicted failure risk for the current change request."""

    result = predict_risk(
        _get_current_change()
    )

    return json.dumps(result)


@tool
def similar_past_changes(k: int = 5) -> str:
    """Find the k most similar past changes and their real outcomes."""

    change = _get_current_change()

    query = change_to_text(
        {
            **change,
            "description": change.get(
                "description",
                "",
            ),
        }
    )

    results = find_similar_changes(
        query,
        k=k,
    )

    return json.dumps(results)


@tool
def incident_history() -> str:
    """Get historical incident information for the affected system."""

    change = _get_current_change()

    return json.dumps(
        get_incident_history(
            change["system"]
        )
    )


@tool
def schedule_conflicts() -> str:
    """Check historical risk and scheduling conflicts for the requested window."""

    change = _get_current_change()

    return json.dumps(
        check_schedule_conflict(
            change["requested_window"]
        )
    )


@tool
def rollback_safety() -> str:
    """Assess the rollback plan safety net for this change."""

    change = _get_current_change()

    return json.dumps(
        get_rollback_status(
            change["rollback_plan_exists"],
            change.get(
                "rollback_plan_tested",
                "None",
            ),
        )
    )


TOOLS = [
    ml_risk_score,
    similar_past_changes,
    incident_history,
    schedule_conflicts,
    rollback_safety,
]


TOOLS_BY_NAME = {
    t.name: t
    for t in TOOLS
}


# -------------------------------------------------------------------
# Autonomous assessment
# -------------------------------------------------------------------

def assess_change_autonomous(
    change: dict,
    max_steps: int = 8,
) -> dict:
    """
    Run the autonomous LangGraph agent.

    The LLM may choose evidence tools, but the final recommendation
    and risk level are always determined by the shared deterministic
    ChangeGuard risk policy.
    """

    # ---------------------------------------------------------------
    # 1. Derive backend historical context
    # ---------------------------------------------------------------

    historical_context = derive_change_context(
        change
    )

    # ---------------------------------------------------------------
    # 2. Build complete 11-feature change
    # ---------------------------------------------------------------

    enriched_change = {
        **change,
        **historical_context,
    }

    _CURRENT_CHANGE.set(
        enriched_change
    )

    # ---------------------------------------------------------------
    # 3. Gather authoritative deterministic evidence
    # ---------------------------------------------------------------
    # These values are used by the shared risk policy.
    # The LLM may gather evidence independently for explanation,
    # but it cannot override this decision.
    # ---------------------------------------------------------------

    query = change_to_text(
        {
            **change,
            "description": change.get(
                "description",
                "",
            ),
        }
    )

    similar_changes = find_similar_changes(
        query,
        k=5,
    )

    schedule_data = check_schedule_conflict(
        change["requested_window"]
    )

    ml_prediction = predict_risk(
        enriched_change
    )

    # ---------------------------------------------------------------
    # 4. Authoritative deterministic risk policy
    # ---------------------------------------------------------------

    policy = calculate_risk_policy(
        ml_prediction,
        change,
        similar_changes,
        schedule_data,
    )

    policy_recommendation = policy[
        "recommendation"
    ]

    policy_risk_level = policy[
        "risk_level"
    ]

    # ---------------------------------------------------------------
    # 5. Autonomous LangGraph loop
    # ---------------------------------------------------------------

    tool_calls_made = []
    llm_justification = None

    if os.environ.get("GROQ_API_KEY"):

        try:
            from langchain_groq import ChatGroq

            autonomous_prompt = SYSTEM_PROMPT + f"""

IMPORTANT DECISION CONTROL:

The authoritative ChangeGuard risk policy has already determined:

RECOMMENDATION: {policy_recommendation}
RISK LEVEL: {policy_risk_level}

You MUST NOT change these values.

You may use the available tools to gather evidence supporting
the explanation.

Your final response must contain ONLY:

JUSTIFICATION: <2-4 sentences using only evidence actually gathered>

Do not output RECOMMENDATION or RISK LEVEL.
Do not create a different recommendation.
Do not create a different risk level.
"""

            llm = ChatGroq(
                model="openai/gpt-oss-120b",
                temperature=0,
            ).bind_tools(
                TOOLS
            )

            # -------------------------------------------------------
            # Model node
            # -------------------------------------------------------

            def call_model(
                state: AgentState,
            ):
                response = llm.invoke(
                    [
                        SystemMessage(
                            content=autonomous_prompt
                        )
                    ]
                    + list(state["messages"])
                )

                return {
                    "messages": [response]
                }

            # -------------------------------------------------------
            # Tool node
            # -------------------------------------------------------

            def call_tools(
                state: AgentState,
            ):
                last = state["messages"][-1]

                outputs = []

                for call in last.tool_calls:
                    tool_name = call["name"]

                    if tool_name not in TOOLS_BY_NAME:
                        raise ValueError(
                            f"Unknown tool requested: {tool_name}"
                        )

                    result = TOOLS_BY_NAME[
                        tool_name
                    ].invoke(
                        call["args"]
                    )

                    outputs.append(
                        ToolMessage(
                            content=str(result),
                            tool_call_id=call["id"],
                            name=tool_name,
                        )
                    )

                return {
                    "messages": outputs
                }

            # -------------------------------------------------------
            # Decide whether another tool round is required
            # -------------------------------------------------------

            def should_continue(
                state: AgentState,
            ):
                last = state["messages"][-1]

                if getattr(
                    last,
                    "tool_calls",
                    None,
                ):
                    return "tools"

                return "end"

            # -------------------------------------------------------
            # Build graph
            # -------------------------------------------------------

            graph = StateGraph(
                AgentState
            )

            graph.add_node(
                "agent",
                call_model,
            )

            graph.add_node(
                "tools",
                call_tools,
            )

            graph.set_entry_point(
                "agent"
            )

            graph.add_conditional_edges(
                "agent",
                should_continue,
                {
                    "tools": "tools",
                    "end": END,
                },
            )

            graph.add_edge(
                "tools",
                "agent",
            )

            compiled_graph = graph.compile()

            # -------------------------------------------------------
            # Initial request
            # -------------------------------------------------------

            initial = (
                "Assess this change request:\n"
                + json.dumps(
                    change,
                    indent=2,
                )
            )

            state = {
                "messages": [
                    HumanMessage(
                        content=initial
                    )
                ]
            }

            # -------------------------------------------------------
            # Execute autonomous graph
            # -------------------------------------------------------

            result_state = compiled_graph.invoke(
                state,
                {
                    "recursion_limit": max_steps * 2
                },
            )

            # -------------------------------------------------------
            # Record tools actually selected by LLM
            # -------------------------------------------------------

            for message in result_state["messages"]:

                if (
                    isinstance(
                        message,
                        AIMessage,
                    )
                    and getattr(
                        message,
                        "tool_calls",
                        None,
                    )
                ):

                    for call in message.tool_calls:
                        tool_calls_made.append(
                            call["name"]
                        )

            # -------------------------------------------------------
            # Extract LLM justification only
            # -------------------------------------------------------

            final_content = (
                result_state["messages"][-1]
                .content
            )

            if isinstance(
                final_content,
                str,
            ):

                llm_justification = (
                    final_content.strip()
                )

                if llm_justification.upper().startswith(
                    "JUSTIFICATION:"
                ):

                    llm_justification = (
                        llm_justification[
                            len("JUSTIFICATION:"):
                        ].strip()
                    )

                if not llm_justification:
                    llm_justification = None

        except Exception as err:

            print(
                "[ChangeGuard LangGraph Warning] "
                f"Autonomous loop error ({err}). "
                "Using deterministic fallback."
            )

    # ---------------------------------------------------------------
    # 6. Deterministic fallback explanation
    # ---------------------------------------------------------------

    if not llm_justification:

        incidents = get_incident_history(
            change["system"]
        )

        rollback = get_rollback_status(
            change["rollback_plan_exists"],
            change.get(
                "rollback_plan_tested",
                "None",
            ),
        )

        justification_parts = []

        prob = ml_prediction.get(
            "risk_probability",
            0.3,
        )

        justification_parts.append(
            f"ML Model predicts a "
            f"{round(prob * 100)}% failure risk "
            f"for {change.get('system', 'this system')}."
        )

        failed_similar_count = policy[
            "failed_similar_count"
        ]

        if len(similar_changes) > 0:

            justification_parts.append(
                f"Historical analysis of "
                f"{len(similar_changes)} similar changes "
                f"showed {failed_similar_count} "
                f"past failures or incidents."
            )

        if incidents.get("note"):

            justification_parts.append(
                incidents["note"]
            )

        if not policy["has_rollback"]:

            justification_parts.append(
                "CRITICAL: No rollback plan is "
                "present for this change."
            )

        elif not policy["tested_rollback"]:

            justification_parts.append(
                "Rollback plan is documented but "
                "has not been tested in staging."
            )

        if policy["has_schedule_conflict"]:

            justification_parts.append(
                f"Scheduled during "
                f"{change.get('requested_window', 'the requested window')} "
                f"with a known scheduling risk."
            )

        llm_justification = " ".join(
            justification_parts
        )

        if not tool_calls_made:

            tool_calls_made = [
                "ml_risk_score",
                "similar_past_changes",
                "incident_history",
                "schedule_conflicts",
                "rollback_safety",
            ]

    # ---------------------------------------------------------------
    # 7. Final answer
    # ---------------------------------------------------------------
    # Recommendation and risk level ALWAYS come from
    # calculate_risk_policy().
    #
    # The LLM can only provide the explanation.
    # ---------------------------------------------------------------

    final_text = (
        f"RECOMMENDATION: "
        f"{policy_recommendation}\n"
        f"RISK LEVEL: "
        f"{policy_risk_level}\n"
        f"JUSTIFICATION: "
        f"{llm_justification}"
    )

    return {
        "final_answer": final_text,
        "tools_called": tool_calls_made,
        "num_tool_calls": len(tool_calls_made),
        "historical_context": historical_context,
        "enriched_change": enriched_change,
        "ml_prediction": ml_prediction,
        "similar_changes": similar_changes,
        "schedule": schedule_data,
        "policy": policy,
    }