"""Medical Research Agent — LangGraph-based workflow with review loop."""

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Annotated, Any

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
from .medical_tools import analyze_symptoms, search_medical_literature, summarize_for_doctor

# Thread-scoped side-channel stores (keyed by thread_id)
_vfs_store: dict[str, dict[str, str]] = defaultdict(dict)
_todos_store: dict[str, list[str]] = defaultdict(list)
_feedback_store: dict[str, list[dict]] = defaultdict(list)


class DeepAgentState(TypedDict):
    messages: Annotated[list, add_messages]
    todos: list[str]
    completed_todos: list[str]
    vfs_keys: list[str]


@tool
def write_file(path: str, content: str, config: RunnableConfig) -> str:
    """Write content to a file in the agent's virtual file system."""
    thread_id = config.get("configurable", {}).get("thread_id", "default")
    _vfs_store[thread_id][path] = content
    return f"File written: {path!r} ({len(content)} chars)"


@tool
def read_file(path: str, config: RunnableConfig) -> str:
    """Read a file from the agent's virtual file system."""
    thread_id = config.get("configurable", {}).get("thread_id", "default")
    vfs = _vfs_store[thread_id]
    if path not in vfs:
        return f"File not found: {path!r}. Available: {list(vfs.keys())}"
    return f"=== {path} ===\n{vfs[path]}"


@tool
def list_files(config: RunnableConfig) -> str:
    """List all files in the agent's virtual file system."""
    thread_id = config.get("configurable", {}).get("thread_id", "default")
    files = list(_vfs_store[thread_id].keys())
    return "VFS files: " + json.dumps(files) if files else "VFS is empty."


@tool
def write_todos(todos: list[str], config: RunnableConfig) -> str:
    """Set the plan for the current research workflow."""
    thread_id = config.get("configurable", {}).get("thread_id", "default")
    _todos_store[thread_id] = todos
    lines = "\n".join(f"  {i+1}. {t}" for i, t in enumerate(todos))
    return f"Plan set ({len(todos)} steps):\n{lines}"


@tool
def request_doctor_review(research_summary: str, config: RunnableConfig) -> str:
    """Submit research findings to a doctor for review."""
    thread_id = config.get("configurable", {}).get("thread_id", "default")

    result = interrupt({
        "question": "Doctor Review: Please review the medical research findings",
        "options": [
            "Accept - Information is accurate and relevant",
            "Reject - Needs refinement (provide feedback)",
        ],
        "research_summary": research_summary,
    })

    decision = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "decision": result,
        "summary": research_summary[:200],
    }
    _feedback_store[thread_id].append(decision)

    if "reject" in str(result).lower() or "feedback" in str(result).lower():
        return (
            "❌ Doctor REJECTED the research findings.\n"
            f"Doctor's decision: {result}\n\n"
            "I will refine my search and find better information based on this feedback."
        )

    return (
        "✅ Doctor ACCEPTED the research findings.\n"
        "The information has been approved and will be shown to the patient."
    )


@tool
def refine_search_with_feedback(original_query: str, feedback: str, config: RunnableConfig) -> str:
    """Use doctor feedback to refine the search strategy."""
    from langchain_core.messages import HumanMessage

    llm = make_llm(MODEL_GENERAL)
    response = llm.invoke([
        SystemMessage(content=(
            "You are a medical research agent. The doctor rejected your previous findings. "
            "Based on their feedback, create a new, more targeted search strategy. "
            "Be specific and actionable."
        )),
        HumanMessage(content=(
            f"Original patient query: {original_query}\n\n"
            f"Doctor's feedback: {feedback}\n\n"
            "What should I search for instead?"
        )),
    ])
    return f"[REFINED SEARCH STRATEGY]\n{response.content}"


SYSTEM_PROMPT = """You are a Medical Research Agent helping patients understand their symptoms through evidence-based research.

YOUR WORKFLOW:
1. ANALYZE SYMPTOMS: Use analyze_symptoms() to understand the patient's problem and create a research plan
2. SEARCH PUBMED: Use search_medical_literature() to find relevant medical research
3. SAVE FINDINGS: Use write_file() to save research articles for reference
4. SUMMARIZE: Use summarize_for_doctor() to create a clear summary of findings
5. DOCTOR REVIEW: Use request_doctor_review() to get doctor approval
   - If ACCEPTED ✅: Research is approved, inform the patient
   - If REJECTED ❌: Use refine_search_with_feedback() and try again with better search

IMPORTANT RULES:
- Always call analyze_symptoms() FIRST to plan your research
- Search PubMed for credible medical sources
- Save all research to VFS using write_file()
- Present findings to a doctor for review before sharing with a patient
- If rejected, learn from feedback and improve your search
- Use proper medical terminology
- Cite PMID numbers for all research
"""

_ALL_TOOLS = [
    write_todos,
    write_file,
    read_file,
    list_files,
    analyze_symptoms,
    search_medical_literature,
    summarize_for_doctor,
    request_doctor_review,
    refine_search_with_feedback,
]


def _agent_node(state: DeepAgentState, config: RunnableConfig) -> dict[str, Any]:
    llm = make_llm(MODEL_GENERAL).bind_tools(_ALL_TOOLS)
    thread_id = config.get("configurable", {}).get("thread_id", "default")

    messages = state["messages"]
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(messages)

    response = llm.invoke(messages, config=config)

    vfs_keys = list(_vfs_store[thread_id].keys())
    todos = _todos_store.get(thread_id, state.get("todos", []))

    return {
        "messages": [response],
        "todos": todos,
        "vfs_keys": vfs_keys,
    }


def _should_continue(state: DeepAgentState) -> str:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return END


def create_deep_agent():
    graph = StateGraph(DeepAgentState)
    graph.add_node("agent", _agent_node)
    graph.add_node("tools", ToolNode(_ALL_TOOLS))
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", _should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile(checkpointer=MemorySaver())


def get_vfs(thread_id: str) -> dict[str, str]:
    return dict(_vfs_store.get(thread_id, {}))


def get_todos(thread_id: str) -> list[str]:
    return list(_todos_store.get(thread_id, []))


def get_feedback_history(thread_id: str) -> list[dict]:
    return list(_feedback_store.get(thread_id, []))


MEDICAL_AGENT = create_deep_agent()
DEEP_AGENT = MEDICAL_AGENT
