"""Minimal simple agent used for compatibility with the demo server APIs."""

from typing import Annotated, Any

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from .config import make_llm, MODEL_GENERAL

_store: dict[str, dict[str, str]] = {}


class SimpleAgentState(TypedDict):
    messages: Annotated[list, add_messages]


@tool
def write_data(key: str, value: str, config: RunnableConfig) -> str:
    """Write a value to the simple agent in-memory store."""
    thread_id = config.get("configurable", {}).get("thread_id", "default")
    _store.setdefault(thread_id, {})[key] = value
    return f"Stored {key!r} = {value!r}"


@tool
def read_data(key: str, config: RunnableConfig) -> str:
    """Read a value from the simple agent in-memory store."""
    thread_id = config.get("configurable", {}).get("thread_id", "default")
    value = _store.get(thread_id, {}).get(key)
    if value is None:
        return f"No value found for key {key!r}."
    return f"{key!r} = {value!r}"


TOOLS = [write_data, read_data]


def _agent_node(state: SimpleAgentState, config: RunnableConfig) -> dict[str, Any]:
    llm = make_llm(MODEL_GENERAL).bind_tools(TOOLS)
    messages = state["messages"]
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content="You are a helpful assistant. Use the available tools when they are useful.")] + list(messages)
    response = llm.invoke(messages, config=config)
    return {"messages": [response]}


def _should_continue(state: SimpleAgentState) -> str:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return END


def create_simple_agent():
    graph = StateGraph(SimpleAgentState)
    graph.add_node("agent", _agent_node)
    graph.add_node("tools", ToolNode(TOOLS))
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", _should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile(checkpointer=MemorySaver())


SIMPLE_AGENT = create_simple_agent()


def get_store_snapshot(thread_id: str) -> dict[str, str]:
    return dict(_store.get(thread_id, {}))
