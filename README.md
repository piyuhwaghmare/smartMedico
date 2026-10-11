# Medical Diagnosis Research Agent

An AI-powered medical research assistant that helps users find relevant medical information from PubMed and other medical databases. Features doctor review (Human-in-the-Loop), feedback-based refinement, and learning from doctor decisions over time. Built on LangGraph with streaming responses and persistent memory.

---

## What's inside

| Component | Description |
|-----------|-------------|
| **Medical Research Agent** | AI agent that searches PubMed and medical databases for symptom/disease information |
| **Doctor Review (HITL)** | Human-in-the-Loop approval system where doctors Accept/Reject research findings |
| **Feedback Loop** | When rejected, agent refines search based on doctor's feedback and tries again |
| **Learning System** | Tracks doctor decisions over time to improve future searches |
| **PubMed Integration** | Searches medical literature using PubMed API |
| **RAG Fallback** | Uses local medical knowledge base when web sources insufficient (to be integrated) |
| **FastAPI Server** | Port 8000. Streaming SSE responses with real-time updates |
| **React Medical UI** | Clean interface for entering symptoms, viewing research, and doctor review |

---

## Prerequisites

- Python 3.11+
- [Ollama](https://ollama.com) running with the following models pulled:

```bash
ollama pull qwen3:8b
ollama pull qwen2.5-coder:14b
ollama pull llama3.1:8b
```

Set `OLLAMA_BASE_URL` in `agents/config.py` if your Ollama is not at `http://10.0.0.224:11434`.

---

## Quick start

```bash
git clone https://github.com/your-org/langgraph-agent-patterns
cd langgraph-agent-patterns
bash run.sh
```

`run.sh` installs dependencies and starts both servers.

| URL | Description |
|-----|-------------|
| `http://localhost:8000` | React GUI (FastAPI mode) |
| `http://localhost:8001` | React GUI (Aegra mode) |
| `http://localhost:8000/presentation` | Reveal.js slide deck |
| `http://localhost:8000/docs` | FastAPI Swagger UI |
| `http://localhost:8001/docs` | Aegra Swagger UI |
| `http://localhost:8000/test` | Minimal SSE diagnostic page |

---

## Project structure

```
agents/
├── agents/
│   ├── config.py          # Ollama URLs and model constants
│   ├── simple_agent.py    # ReAct agent — write/read/list_data tools
│   ├── skills.py          # analyze_data, write_code, search_knowledge
│   └── deep_agent.py      # StateGraph: VFS + todos + skills + HITL
├── servers/
│   ├── fastapi_server.py  # Raw SSE, custom event schema (port 8000)
│   └── aegra_server.py    # LangGraph Platform REST API (port 8001)
├── frontend/
│   ├── index.html         # React 18 GUI (CDN, no build)
│   └── test.html          # Plain XHR SSE diagnostic
├── presentation/
│   └── index.html         # Reveal.js slides
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── run.sh
```

---

## Example prompts

**Simple agent**
```
Write name=Alice role=engineer to the data store, then read it back.
```

**Deep agent — planning + skills**
```
Analyze this dataset: sales=120, users=80, churn=5%.
Save findings to report.txt and write Python to plot the data.
```

**Deep agent — HITL**
```
Search for sales trends, then ask me how detailed the report should be.
```

---

## API reference

### FastAPI (port 8000)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/simple/stream` | Stream simple agent — body: `{message, thread_id}` |
| `POST` | `/api/deep/stream` | Stream deep agent — body: `{message, thread_id}` |
| `POST` | `/api/resume/{thread_id}` | Resume HITL interrupt — body: `{choice}` |
| `GET`  | `/api/threads/{id}/vfs` | VFS file snapshot |
| `GET`  | `/api/threads/{id}/todos` | Todo list snapshot |
| `GET`  | `/api/store` | Simple agent KV store |
| `GET`  | `/api/test/stream` | Mock SSE stream (no Ollama needed) |

SSE event format:
```
data: {"type": "token",      "content": "..."}
data: {"type": "tool_start", "tool": "write_file", "input": {...}}
data: {"type": "tool_end",   "tool": "write_file", "output": "..."}
data: {"type": "vfs_update", "files": {...}}
data: {"type": "interrupt",  "question": "...", "options": [...]}
data: {"type": "done"}
```

### Aegra (port 8001)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/assistants` | List available agents |
| `POST` | `/threads` | Create a thread |
| `GET`  | `/threads/{id}` | Thread metadata |
| `GET`  | `/threads/{id}/state` | Full state snapshot |
| `POST` | `/threads/{id}/runs/stream` | Stream a run — body: `{assistant_id, input}` |
| `POST` | `/threads/{id}/runs/{rid}/resume` | Resume interrupt — body: `{values}` |
| `GET`  | `/threads/{id}/runs` | List runs for thread |

SSE event names: `metadata` · `updates` · `messages/partial` · `tool_start` · `tool_end` · `interrupt` · `values` · `end`

---

## Architecture notes

### Why two servers?

FastAPI raw SSE is the path most teams start on — it's quick to wire up but creates a tight client/server coupling around a custom event schema. Aegra implements the open [LangGraph Platform REST spec](https://langchain-ai.github.io/langgraph/concepts/langgraph_server/), so any client that speaks the SDK (JS, Python, LangFlow) works against it without modification.

The same LangGraph agent code runs behind both. The server layer is the only difference.

### Deep Agent internals

The Deep Agent is a hand-authored `StateGraph` rather than `create_react_agent`. This gives explicit control over:

- **VFS** — files written by the agent live in a per-thread dict, not in the context window. The LLM writes a path; humans or tools read it back.
- **Todos** — the agent can call `write_todos` to publish its plan before executing it. Clients see the plan in real time.
- **Skills bus** — `analyze_data`, `write_code`, and `search_knowledge` are LangGraph tools that each spin up their own `ChatOllama` instance. The orchestrator model chooses which skill to invoke; the skill model does the specialised work.
- **HITL** — `request_options` calls `interrupt()`, which serializes the full graph state to `MemorySaver`. The agent is paused until `Command(resume=choice)` is sent.

### Nesting LangGraph agents

Any compiled LangGraph graph can be wrapped as a tool and given to a parent agent. This is how the Deep Agent pattern scales: a top-level orchestrator graph calls sub-graphs (the skills) as opaque tools, each with their own state and checkpointer if needed.

```python
@tool
def run_sub_agent(task: str, config: RunnableConfig) -> str:
    """Delegate a task to the specialized sub-agent."""
    result = SUB_AGENT.invoke(
        {"messages": [{"role": "user", "content": task}]},
        config=config
    )
    return result["messages"][-1].content
```

---

## Docker

```bash
docker compose up
```

Both servers start on ports 8000 and 8001. Set `OLLAMA_BASE_URL` as an environment variable to point at your Ollama host.

---

## Stack

| Layer | Library | License |
|-------|---------|---------|
| Agent framework | LangGraph | MIT |
| LLM interface | LangChain + langchain-ollama | MIT |
| HTTP server | FastAPI + uvicorn | MIT |
| SSE | sse-starlette | BSD |
| Platform API | Aegra pattern | Apache 2.0 |
| Frontend | React 18 (CDN) | MIT |
| Presentation | Reveal.js (CDN) | MIT |
| Models | Ollama (local) | MIT |
