"""
Medical Research Agent — searches PubMed for symptom-based diagnosis information
and requires doctor approval (Human-in-the-Loop) before showing results to patient.

Workflow:
1. Patient enters symptoms
2. Agent searches PubMed for relevant medical information
3. Doctor reviews findings (Accept/Reject with feedback)
4. If rejected: Agent searches again with doctor's feedback
5. If accepted: Show information to patient
"""

from typing import Annotated, Any
from collections import defaultdict

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt
from typing_extensions import TypedDict

from .config import make_llm, MODEL_GENERAL

# Thread-scoped storage
_search_results: dict[str, list] = defaultdict(list)
_approved_results: dict[str, list] = defaultdict(list)
_feedback_history: dict[str, list] = defaultdict(list)


# ── State ────────────────────────────────────────────────────────────────────

class MedicalAgentState(TypedDict):
    messages: Annotated[list, add_messages]
    search_results: list[dict]
    approved_results: list[dict]
    awaiting_approval: bool


# ── Tools ────────────────────────────────────────────────────────────────────

@tool
def search_pubmed(query: str, config: RunnableConfig) -> str:
    """
    Search PubMed for medical research articles based on symptoms or conditions.
    Returns relevant abstracts and citations.
    """
    thread_id = config.get("configurable", {}).get("thread_id", "default")
    
    # Simulate PubMed search results
    # In production, replace with actual PubMed API call
    mock_results = [
        {
            "title": f"Clinical Study: {query}",
            "abstract": f"Research findings related to {query}. This is a simulated abstract from PubMed. Symptoms may include various manifestations. Diagnosis requires clinical examination. Treatment options should be discussed with healthcare provider.",
            "pmid": "12345678",
            "authors": "Smith J, et al.",
            "year": "2023",
            "relevance_score": 0.95
        },
        {
            "title": f"Systematic Review: Management of {query}",
            "abstract": f"Comprehensive review of {query} cases. Evidence-based approach to diagnosis and treatment. Multiple studies analyzed for best practices.",
            "pmid": "87654321",
            "authors": "Johnson A, Brown B, et al.",
            "year": "2024",
            "relevance_score": 0.88
        }
    ]
    
    _search_results[thread_id] = mock_results
    
    summary = f"Found {len(mock_results)} relevant articles:\n\n"
    for i, result in enumerate(mock_results, 1):
        summary += f"{i}. {result['title']}\n"
        summary += f"   Authors: {result['authors']} ({result['year']})\n"
        summary += f"   PMID: {result['pmid']}\n"
        summary += f"   Abstract: {result['abstract'][:200]}...\n\n"
    
    return summary


@tool
def request_doctor_approval(
    findings: str,
    sources: str,
    config: RunnableConfig
) -> str:
    """
    Submit medical findings to doctor for approval before showing to patient.
    Doctor can either approve or reject with feedback for improvement.
    
    Args:
        findings: Summary of medical findings to show patient
        sources: List of PubMed sources used
    """
    thread_id = config.get("configurable", {}).get("thread_id", "default")
    
    # Prepare approval request
    approval_data = {
        "question": "Review the following medical findings. Do you approve showing this to the patient?",
        "findings": findings,
        "sources": sources,
        "options": [
            "✅ Approve - Show to patient",
            "❌ Reject - Needs improvement",
            "⚠️ Reject - Search for more specific information"
        ]
    }
    
    # LangGraph interrupt — pauses the graph and surfaces data to the GUI
    choice = interrupt(approval_data)
    
    # Process doctor's decision
    if "Approve" in choice:
        _approved_results[thread_id].append({
            "findings": findings,
            "sources": sources,
            "status": "approved"
        })
        _feedback_history[thread_id].append({
            "decision": "approved",
            "feedback": "Information approved for patient viewing"
        })
        return f"✅ Doctor approved. Patient can now view the findings."
    else:
        feedback = choice.split("-")[1].strip() if "-" in choice else "needs improvement"
        _feedback_history[thread_id].append({
            "decision": "rejected",
            "feedback": feedback
        })
        return f"❌ Doctor rejected: {feedback}. Please search for more relevant information."


@tool
def get_approved_findings(config: RunnableConfig) -> str:
    """
    Retrieve the approved medical findings for display to patient.
    Only shows information that has been verified by a doctor.
    """
    thread_id = config.get("configurable", {}).get("thread_id", "default")
    
    approved = _approved_results[thread_id]
    
    if not approved:
        return "No approved findings yet. Doctor review is still pending."
    
    latest = approved[-1]
    output = "=== DOCTOR-APPROVED MEDICAL INFORMATION ===\n\n"
    output += latest["findings"] + "\n\n"
    output += "SOURCES:\n" + latest["sources"] + "\n\n"
    output += "⚕️ This information has been reviewed and approved by a medical professional."
    
    return output


# ── Graph ─────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a Medical Research Assistant AI helping patients understand their symptoms.

IMPORTANT RULES:
1. You are NOT a doctor and cannot provide medical diagnoses
2. All information you find must be reviewed by a real doctor before showing to patients
3. Always cite PubMed sources with PMID numbers
4. If doctor rejects your findings, search again with better queries

WORKFLOW:
1. When patient describes symptoms, use search_pubmed to find relevant research
2. Summarize findings clearly and cite all sources
3. Use request_doctor_approval to submit findings for doctor review
4. If approved: Use get_approved_findings to show patient the verified information
5. If rejected: Search again with improved query based on doctor's feedback

TONE: Professional, compassionate, and clear. Always remind patients to consult healthcare providers.
"""

_ALL_TOOLS = [
    search_pubmed,
    request_doctor_approval,
    get_approved_findings,
]


def _agent_node(state: MedicalAgentState, config: RunnableConfig) -> dict[str, Any]:
    llm = make_llm(MODEL_GENERAL).bind_tools(_ALL_TOOLS)
    thread_id = config.get("configurable", {}).get("thread_id", "default")

    messages = state["messages"]
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(messages)

    response = llm.invoke(messages, config=config)

    # Sync state with side-channel stores
    search_results = _search_results.get(thread_id, [])
    approved = _approved_results.get(thread_id, [])

    return {
        "messages": [response],
        "search_results": search_results,
        "approved_results": approved,
        "awaiting_approval": False,
    }


def _should_continue(state: MedicalAgentState) -> str:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return END


def create_medical_agent():
    graph = StateGraph(MedicalAgentState)
    graph.add_node("agent", _agent_node)
    graph.add_node("tools", ToolNode(_ALL_TOOLS))
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", _should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    memory = MemorySaver()
    return graph.compile(checkpointer=memory)


# Expose side-channel accessors for servers
def get_search_results(thread_id: str) -> list:
    return list(_search_results.get(thread_id, []))


def get_approved_results(thread_id: str) -> list:
    return list(_approved_results.get(thread_id, []))


def get_feedback_history(thread_id: str) -> list:
    return list(_feedback_history.get(thread_id, []))


MEDICAL_AGENT = create_medical_agent()
