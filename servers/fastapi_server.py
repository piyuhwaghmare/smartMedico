"""
FastAPI Server — RAW SSE approach (port 8000).

Key characteristic: you manually translate astream_events into a custom
hand-rolled JSON event schema. The frontend must know and parse this schema.
No standard contract — tight coupling between server and client.
"""

import json
import uuid
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from langgraph.types import Command
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from agents.deep_agent import MEDICAL_AGENT, get_todos, get_vfs, get_feedback_history

# Doctor review queue
pending_reviews = {}  # thread_id -> {query, ai_summary, sources, timestamp}

app = FastAPI(title="DeepAgent Demo — FastAPI (Raw SSE)", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
PRESENTATION_DIR = Path(__file__).parent.parent / "presentation"


# ── Request Models ────────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    message: str
    thread_id: str = ""


class ResumeRequest(BaseModel):
    choice: str


# ── SSE Helpers ───────────────────────────────────────────────────────────────

def _sse(payload: dict) -> str:
    """Serialize one SSE data line."""
    return json.dumps(payload)


async def _stream_agent(agent, message: str, thread_id: str):
    """
    RAW SSE generator — manually maps astream_events to a custom event schema.
    This is the FastAPI "manual" approach: explicit if/elif on event_name.
    """
    config = {"configurable": {"thread_id": thread_id}}
    inputs = {"messages": [{"role": "user", "content": message}]}

    try:
        async for event in agent.astream_events(inputs, config=config, version="v2"):
            name = event.get("event", "")
            data = event.get("data", {})
            tags = event.get("tags", [])

            if name == "on_chat_model_stream":
                chunk = data.get("chunk", {})
                content = getattr(chunk, "content", "") or ""
                if content:
                    yield _sse({"type": "token", "content": content})

            elif name == "on_tool_start":
                yield _sse({
                    "type": "tool_start",
                    "tool": event.get("name", ""),
                    "input": data.get("input", {}),
                })

            elif name == "on_tool_end":
                output = data.get("output", "")
                if hasattr(output, "content"):
                    output = output.content
                yield _sse({
                    "type": "tool_end",
                    "tool": event.get("name", ""),
                    "output": str(output)[:500],
                })

                # Sync side-panel state after each tool
                vfs = get_vfs(thread_id)
                todos = get_todos(thread_id)
                if vfs:
                    yield _sse({"type": "vfs_update", "files": vfs})
                if todos:
                    yield _sse({"type": "todos_update", "todos": todos})

    except Exception as exc:
        error_str = str(exc)
        # LangGraph surfaces HITL as a GraphInterrupt exception
        if "GraphInterrupt" in type(exc).__name__ or "__interrupt__" in error_str:
            import re
            # Extract interrupt payload if possible
            try:
                payload = exc.args[0] if exc.args else {}
                if isinstance(payload, (list, tuple)) and len(payload) > 0:
                    interrupt_val = payload[0].value if hasattr(payload[0], "value") else payload[0]
                else:
                    interrupt_val = payload
                yield _sse({
                    "type": "interrupt",
                    "question": interrupt_val.get("question", "Please choose:") if isinstance(interrupt_val, dict) else str(interrupt_val),
                    "options": interrupt_val.get("options", []) if isinstance(interrupt_val, dict) else [],
                })
            except Exception:
                yield _sse({"type": "interrupt", "question": "Agent needs input", "options": []})
            return

        yield _sse({"type": "error", "message": error_str})
        return

    yield _sse({"type": "done"})


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/test/stream")
async def test_stream():
    """Instant mock SSE — no Ollama needed. Use to verify browser SSE pipeline."""
    import asyncio

    async def generator():
        for chunk in ["Hello ", "from ", "the ", "agent! "]:
            yield {"data": json.dumps({"type": "token", "content": chunk})}
            await asyncio.sleep(0.3)
        yield {"data": json.dumps({"type": "tool_start", "tool": "write_data", "input": {"key": "demo", "value": "works"}})}
        await asyncio.sleep(0.4)
        yield {"data": json.dumps({"type": "tool_end", "tool": "write_data", "output": "Stored: 'demo' = 'works'"})}
        await asyncio.sleep(0.3)
        for chunk in ["SSE ", "pipeline ", "is ", "working ✓"]:
            yield {"data": json.dumps({"type": "token", "content": chunk})}
            await asyncio.sleep(0.2)
        yield {"data": json.dumps({"type": "done"})}

    return EventSourceResponse(generator())


@app.post("/api/medical/stream")
async def stream_medical(req: RunRequest):
    """Stream the RAG-powered medical agent - searches multiple sources, uses vector DB + LLM"""
    thread_id = req.thread_id or str(uuid.uuid4())
    
    config = {"configurable": {"thread_id": thread_id}}
    
    # State for RAG agent
    inputs = {
        "messages": [{"role": "user", "content": req.message}],
        "query": req.message,
        "raw_documents": [],
        "llm_summary": "",
        "search_done": False,
        "synthesis_done": False,
    }

    async def generator():
        try:
            # Stream all events from RAG agent
            async for event in MEDICAL_AGENT.astream_events(inputs, config=config, version="v2"):
                name = event.get("event", "")
                data = event.get("data", {})
                node_name = event.get("name", "")

                # Stream node outputs (search, synthesize, approve)
                if name == "on_chain_end" and node_name in ("search", "synthesize", "approve"):
                    output = data.get("output", {})
                    messages = output.get("messages", [])
                    if messages:
                        last_msg = messages[-1]
                        content = getattr(last_msg, "content", str(last_msg))
                        if content:
                            yield {"data": json.dumps({"type": "token", "content": content})}

        except Exception as exc:
            error_type = type(exc).__name__
            
            # Handle HITL interrupt (doctor approval)
            if "GraphInterrupt" in error_type or "interrupt" in str(exc).lower():
                try:
                    payload = exc.args[0] if exc.args else {}
                    
                    if isinstance(payload, (list, tuple)) and payload:
                        interrupt_val = payload[0].value if hasattr(payload[0], "value") else payload[0]
                    else:
                        interrupt_val = payload
                    
                    # ADD TO DOCTOR PENDING QUEUE
                    if isinstance(interrupt_val, dict):
                        pending_reviews[thread_id] = {
                            "thread_id": thread_id,
                            "query": req.message,
                            "ai_summary": interrupt_val.get("findings", ""),
                            "sources": interrupt_val.get("sources", ""),
                            "timestamp": __import__("time").time()
                        }
                        print(f"[HITL] Added to doctor queue: {thread_id}")
                    
                    # Tell patient to wait for doctor
                    yield {"data": json.dumps({
                        "type": "token",
                        "content": "\n\n⏳ **Awaiting Doctor Approval**\n\nYour query has been sent to a medical professional for review. Please wait..."
                    })}
                    yield {"data": json.dumps({"type": "done"})}
                    
                except Exception as e:
                    print(f"Interrupt parsing error: {e}")
                    import traceback
                    traceback.print_exc()
                return

            # Other errors
            print(f"Stream error ({error_type}): {exc}")
            import traceback
            traceback.print_exc()
            yield {"data": json.dumps({"type": "error", "message": f"{error_type}: {str(exc)}"})}
            return

        yield {"data": json.dumps({"type": "done"})}

    return EventSourceResponse(generator())


@app.post("/api/resume/{thread_id}")
async def resume_thread(thread_id: str, req: ResumeRequest):
    """Resume an interrupted medical agent thread with doctor's decision."""
    config = {"configurable": {"thread_id": thread_id}}

    events = []
    try:
        async for event in MEDICAL_AGENT.astream_events(
            Command(resume=req.choice), config=config, version="v2"
        ):
            name = event.get("event", "")
            data = event.get("data", {})
            if name == "on_chat_model_stream":
                chunk = data.get("chunk", {})
                content = getattr(chunk, "content", "") or ""
                if content:
                    events.append({"type": "token", "content": content})
            elif name == "on_tool_end":
                output = data.get("output", "")
                events.append({"type": "tool_end", "tool": event.get("name"), "output": str(output)[:300]})
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

    vfs = get_vfs(thread_id)
    todos = get_todos(thread_id)
    feedback = get_feedback_history(thread_id)
    return {
        "status": "resumed",
        "thread_id": thread_id,
        "events": events,
        "vfs": vfs,
        "todos": todos,
        "feedback_count": len(feedback),
    }


@app.get("/api/threads/{thread_id}/vfs")
async def get_thread_vfs(thread_id: str):
    return {"thread_id": thread_id, "files": get_vfs(thread_id)}


@app.get("/api/threads/{thread_id}/feedback")
async def get_thread_feedback(thread_id: str):
    """Get doctor feedback history for learning/analytics."""
    return {"thread_id": thread_id, "feedback_history": get_feedback_history(thread_id)}


@app.get("/api/threads/{thread_id}/todos")
async def get_thread_todos(thread_id: str):
    return {"thread_id": thread_id, "todos": get_todos(thread_id)}


# ── Static Files ──────────────────────────────────────────────────────────────

@app.get("/doctor")
async def doctor_dashboard():
    """Doctor dashboard page"""
    return FileResponse(FRONTEND_DIR / "doctor.html")


@app.get("/api/doctor/pending")
async def get_pending_reviews():
    """Get all pending reviews for doctor"""
    return {"pending": list(pending_reviews.values())}


@app.get("/api/patient/status/{thread_id}")
async def get_patient_status(thread_id: str):
    """Check if doctor has responded - for patient polling"""
    print(f"[STATUS CHECK] Thread {thread_id}")
    
    # Still pending doctor review
    if thread_id in pending_reviews:
        return {
            "status": "pending",
            "message": "Waiting for doctor review"
        }
    
    # Check if there's a completed result in the graph state
    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = MEDICAL_AGENT.get_state(config)
        messages = state.values.get("messages", [])
        
        if messages:
            # Get the last message
            last_msg = messages[-1]
            content = getattr(last_msg, "content", str(last_msg))
            
            # Check if it's an approval or rejection message
            if "DOCTOR APPROVED" in content or "Doctor feedback" in content:
                print(f"[STATUS CHECK] Thread {thread_id} completed")
                return {
                    "status": "completed",
                    "result": content
                }
        
        # If no clear result yet, still waiting
        return {
            "status": "pending",
            "message": "Processing..."
        }
        
    except Exception as e:
        print(f"[STATUS CHECK ERROR] {e}")
        return {
            "status": "unknown",
            "message": "Could not retrieve status"
        }


@app.post("/api/doctor/approve/{thread_id}")
async def approve_review(thread_id: str):
    """Doctor approves the AI response - properly resumes the graph"""
    if thread_id not in pending_reviews:
        return {"status": "not_found", "message": "No pending review for this thread"}
    
    review_data = pending_reviews[thread_id]
    config = {"configurable": {"thread_id": thread_id}}
    
    print(f"[APPROVE] Doctor approving thread {thread_id}")
    
    try:
        # Resume the graph with approval using Command
        result_messages = []
        async for event in MEDICAL_AGENT.astream_events(
            Command(resume="✅ Approve - Information is accurate"),
            config=config,
            version="v2"
        ):
            name = event.get("event", "")
            data = event.get("data", {})
            node_name = event.get("name", "")
            
            # Capture node outputs
            if name == "on_chain_end" and node_name in ("approve",):
                output = data.get("output", {})
                messages = output.get("messages", [])
                if messages:
                    last_msg = messages[-1]
                    content = getattr(last_msg, "content", str(last_msg))
                    if content:
                        result_messages.append(content)
                        print(f"[APPROVE] Result: {content[:100]}...")
        
        # Remove from pending queue
        del pending_reviews[thread_id]
        
        print(f"[APPROVE] ✅ Thread {thread_id} approved and resumed")
        
        return {
            "status": "approved",
            "thread_id": thread_id,
            "result": result_messages
        }
    except Exception as e:
        print(f"[APPROVE ERROR] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.post("/api/doctor/reject/{thread_id}")
async def reject_review(thread_id: str, feedback: dict):
    """Doctor rejects with feedback - properly resumes the graph"""
    if thread_id not in pending_reviews:
        return {"status": "not_found", "message": "No pending review for this thread"}
    
    review_data = pending_reviews[thread_id]
    config = {"configurable": {"thread_id": thread_id}}
    feedback_text = feedback.get("feedback", "Needs improvement")
    
    print(f"[REJECT] Doctor rejecting thread {thread_id} with feedback: {feedback_text}")
    
    try:
        # Resume the graph with rejection using Command
        result_messages = []
        async for event in MEDICAL_AGENT.astream_events(
            Command(resume=f"❌ Reject - {feedback_text}"),
            config=config,
            version="v2"
        ):
            name = event.get("event", "")
            data = event.get("data", {})
            node_name = event.get("name", "")
            
            # Capture node outputs
            if name == "on_chain_end" and node_name in ("approve",):
                output = data.get("output", {})
                messages = output.get("messages", [])
                if messages:
                    last_msg = messages[-1]
                    content = getattr(last_msg, "content", str(last_msg))
                    if content:
                        result_messages.append(content)
                        print(f"[REJECT] Result: {content[:100]}...")
        
        # Remove from pending queue
        del pending_reviews[thread_id]
        
        print(f"[REJECT] ✅ Thread {thread_id} rejected and resumed")
        
        return {
            "status": "rejected",
            "thread_id": thread_id,
            "feedback": feedback_text,
            "result": result_messages
        }
    except Exception as e:
        print(f"[REJECT ERROR] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@app.get("/test")
async def test_page():
    return FileResponse(FRONTEND_DIR / "test.html")


@app.get("/medical.html")
async def medical_page():
    return FileResponse(FRONTEND_DIR / "medical.html")


@app.get("/medical")
async def medical_page_alt():
    return FileResponse(FRONTEND_DIR / "medical.html")


@app.get("/presentation")
async def presentation():
    return FileResponse(PRESENTATION_DIR / "index.html")


@app.get("/")
async def index():
    """Redirect to medical UI by default."""
    return FileResponse(FRONTEND_DIR / "medical.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("servers.fastapi_server:app", host="0.0.0.0", port=8000, reload=True)
