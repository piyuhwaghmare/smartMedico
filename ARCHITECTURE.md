# Medical Research Agent - Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND (Browser)                       │
│                      frontend/medical.html                       │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   Patient    │  │   Doctor     │  │  Research    │         │
│  │    Input     │  │   Review     │  │   Status     │         │
│  │              │  │    Modal     │  │   Sidebar    │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTP/SSE
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FASTAPI SERVER (Port 8000)                    │
│                  servers/fastapi_server.py                       │
│                                                                  │
│  Endpoints:                                                      │
│  • POST /api/medical/stream  → Start medical query              │
│  • POST /api/resume/{id}     → Resume after doctor review       │
│  • GET  /api/threads/{id}/feedback → Get learning data          │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                     MEDICAL AGENT                                │
│                  agents/deep_agent.py                            │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐    │
│  │  LangGraph StateGraph                                  │    │
│  │                                                        │    │
│  │  State:                                               │    │
│  │  • messages: Conversation history                     │    │
│  │  • todos: Research plan steps                         │    │
│  │  • vfs_keys: Saved research files                     │    │
│  │  • feedback: Doctor decisions (learning data)         │    │
│  └────────────────────────────────────────────────────────┘    │
│                                                                  │
│  Tools Available:                                                │
│  1. analyze_symptoms        → Understand patient problem         │
│  2. search_medical_literature → PubMed API search               │
│  3. summarize_for_doctor    → Create review summary             │
│  4. request_doctor_review   → Human-in-the-Loop pause           │
│  5. refine_search_with_feedback → Improve after rejection       │
│  6. write_file / read_file  → Store research articles           │
└───────────┬─────────────────────┬───────────────────────────────┘
            │                     │
            ▼                     ▼
┌───────────────────┐   ┌──────────────────────────┐
│   MEDICAL TOOLS   │   │   OLLAMA LLM             │
│ medical_tools.py  │   │   agents/config.py       │
│                   │   │                          │
│ • PubMed API      │   │ Model: qwen3:8b          │
│ • Symptom Analysis│   │ Port: 11434              │
│ • Summarization   │   │                          │
└───────────────────┘   └──────────────────────────┘
```

## Data Flow - Patient Query to Doctor Review

```
┌──────────────────────────────────────────────────────────────────┐
│ 1. PATIENT ENTERS SYMPTOMS                                       │
│    "I have a headache for 3 days with fever and nausea"          │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ 2. AGENT ANALYZES (Tool: analyze_symptoms)                       │
│    ┌─────────────────────────────────────────────────┐          │
│    │ LLM Call:                                        │          │
│    │ "Extract key symptoms and suggest search terms"  │          │
│    │                                                  │          │
│    │ Output:                                          │          │
│    │ • Key symptoms: headache, fever, nausea          │          │
│    │ • Duration: 3 days                               │          │
│    │ • Search terms: "headache fever nausea causes"   │          │
│    │ • Possible conditions: migraine, infection       │          │
│    └─────────────────────────────────────────────────┘          │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ 3. AGENT SEARCHES PUBMED (Tool: search_medical_literature)       │
│    ┌─────────────────────────────────────────────────┐          │
│    │ HTTP Request to PubMed API:                      │          │
│    │ https://eutils.ncbi.nlm.nih.gov/entrez/eutils/  │          │
│    │                                                  │          │
│    │ Returns:                                         │          │
│    │ • Article 1: PMID 12345678                       │          │
│    │   Title: "Migraine with aura symptoms..."        │          │
│    │   Abstract: "Headache accompanied by..."         │          │
│    │   Year: 2023                                     │          │
│    │                                                  │          │
│    │ • Article 2-5: Similar format                    │          │
│    └─────────────────────────────────────────────────┘          │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ 4. AGENT SAVES RESEARCH (Tool: write_file)                       │
│    ┌─────────────────────────────────────────────────┐          │
│    │ VFS (Virtual File System):                       │          │
│    │                                                  │          │
│    │ research_headache.txt:                           │          │
│    │ "Found 5 articles about headache with fever..."  │          │
│    │                                                  │          │
│    │ pubmed_articles_20240115.txt:                    │          │
│    │ "Full article details with PMIDs..."             │          │
│    └─────────────────────────────────────────────────┘          │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ 5. AGENT SUMMARIZES (Tool: summarize_for_doctor)                │
│    ┌─────────────────────────────────────────────────┐          │
│    │ LLM Call:                                        │          │
│    │ "Create structured summary for doctor review"    │          │
│    │                                                  │          │
│    │ Output:                                          │          │
│    │ KEY FINDINGS:                                    │          │
│    │ • Headache + fever + nausea common in:           │          │
│    │   - Migraine with aura (3 studies)               │          │
│    │   - Viral meningitis (2 studies)                 │          │
│    │                                                  │          │
│    │ EVIDENCE QUALITY:                                │          │
│    │ • Recent studies (2022-2023)                     │          │
│    │ • Sample sizes: 200-500 patients                 │          │
│    │                                                  │          │
│    │ RECOMMENDATIONS:                                 │          │
│    │ • Consider neurological examination              │          │
│    │ • Rule out infection                             │          │
│    └─────────────────────────────────────────────────┘          │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ 6. DOCTOR REVIEW (Tool: request_doctor_review)                  │
│    ┌─────────────────────────────────────────────────┐          │
│    │ LangGraph interrupt() called                     │          │
│    │                                                  │          │
│    │ Modal shows in UI:                               │          │
│    │ ┌───────────────────────────────────────────┐   │          │
│    │ │ 👨‍⚕️ Doctor Review Required              │   │          │
│    │ │                                           │   │          │
│    │ │ [Summary displayed here]                  │   │          │
│    │ │                                           │   │          │
│    │ │ ✅ Accept - Approve for patient          │   │          │
│    │ │ ❌ Reject - Request refinement           │   │          │
│    │ └───────────────────────────────────────────┘   │          │
│    │                                                  │          │
│    │ Agent execution PAUSED until doctor responds     │          │
│    └─────────────────────────────────────────────────┘          │
└────────────────┬─────────────────────────────────────────────────┘
                 │
         ┌───────┴────────┐
         │                │
    ACCEPT            REJECT
         │                │
         ▼                ▼
┌─────────────────┐  ┌──────────────────────────────────────┐
│ 7a. APPROVED    │  │ 7b. REFINE SEARCH                    │
│                 │  │    (Tool: refine_search_with_feedback)│
│ • Show to       │  │                                       │
│   patient       │  │ LLM analyzes rejection:              │
│                 │  │ "Doctor said: too old studies"       │
│ • Save feedback │  │                                       │
│   as "Accept"   │  │ New strategy:                        │
│                 │  │ • Search only 2023-2024 articles     │
│ • Learning:     │  │ • Add "recent" to search terms       │
│   Pattern +1    │  │ • Focus on meta-analyses             │
│                 │  │                                       │
│ ✅ DONE         │  │ Goes back to step 3 (PubMed search)  │
└─────────────────┘  └──────────────────────────────────────┘
```

## Component Details

### 1. Frontend (medical.html)

**Tech Stack:**
- React 18 (CDN - no build required)
- Pure CSS (no frameworks)
- Server-Sent Events (SSE) for streaming

**Key Features:**
- Real-time token streaming
- Tool execution visualization
- Doctor review modal (HITL)
- Research status sidebar
- Saved files display

**SSE Events Handled:**
```javascript
{type: 'token'}         → Append to AI message
{type: 'tool_start'}    → Show tool execution
{type: 'tool_end'}      → Show tool result
{type: 'todos_update'}  → Update research plan
{type: 'vfs_update'}    → Update saved files
{type: 'interrupt'}     → Show doctor modal
{type: 'done'}          → Mark complete
```

### 2. FastAPI Server

**Endpoints:**

```python
POST /api/medical/stream
  • Streams medical agent responses
  • Returns SSE events
  • Handles GraphInterrupt for HITL

POST /api/resume/{thread_id}
  • Resumes paused agent
  • Accepts doctor's choice
  • Returns continuation events

GET /api/threads/{id}/feedback
  • Returns learning history
  • Format: [{timestamp, decision, summary}]
```

### 3. Medical Agent (LangGraph)

**State Schema:**
```python
class DeepAgentState(TypedDict):
    messages: list           # Conversation history
    todos: list[str]         # Research plan steps
    vfs_keys: list[str]      # Saved file paths
```

**Tool Execution Flow:**
1. LLM decides which tool to call
2. Tool executes (e.g., PubMed API)
3. Result returned to LLM
4. LLM decides next action
5. Repeat until done or interrupt

### 4. Medical Tools

**PubMed Integration:**
```python
def search_pubmed(query, max_results=5):
    # Step 1: Search for article IDs
    response = requests.get(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        params={
            "db": "pubmed",
            "term": query,
            "retmax": max_results
        }
    )
    
    # Step 2: Fetch article details
    # Step 3: Parse XML
    # Step 4: Extract title, abstract, PMID
    
    return articles
```

## Learning System Architecture

### Current Implementation (Simple Tracking)

```
┌─────────────────────────────────────────────────────────┐
│  FEEDBACK STORE (In-Memory)                             │
│                                                          │
│  _feedback_store[thread_id] = [                         │
│    {                                                     │
│      "timestamp": "2024-01-15T10:30:00",                │
│      "decision": "Accept - Accurate information",       │
│      "summary": "Research about headaches...",          │
│    },                                                    │
│    {                                                     │
│      "timestamp": "2024-01-15T10:35:00",                │
│      "decision": "Reject - Too old, need recent",       │
│      "summary": "Research about fever...",              │
│    }                                                     │
│  ]                                                       │
└─────────────────────────────────────────────────────────┘
```

### Future Implementation (Pattern Learning)

```
┌─────────────────────────────────────────────────────────┐
│  LEARNING PIPELINE (To Be Added)                        │
│                                                          │
│  1. COLLECT                                              │
│     • Every Accept/Reject decision                       │
│     • Associated search terms                            │
│     • Article characteristics (year, source, type)       │
│                                                          │
│  2. ANALYZE                                              │
│     • Pattern detection:                                 │
│       "Doctor always rejects studies >5 years old"       │
│       "Doctor prefers meta-analyses over case studies"   │
│       "Doctor accepts specific journals: NEJM, Lancet"   │
│                                                          │
│  3. APPLY                                                │
│     • Modify search strategy automatically:              │
│       - Filter by year: 2019-2024                        │
│       - Prioritize: "meta-analysis" OR "systematic review"│
│       - Add journal filter to PubMed query               │
│                                                          │
│  4. IMPROVE                                              │
│     • Track acceptance rate over time                    │
│     • A/B test different strategies                      │
│     • Continuous refinement                              │
└─────────────────────────────────────────────────────────┘
```

## Technology Stack

```
┌──────────────────────────────────────────────────────────┐
│  LAYER              TECHNOLOGY                            │
├──────────────────────────────────────────────────────────┤
│  Frontend           React 18 (CDN), Vanilla CSS           │
│  HTTP Server        FastAPI, Uvicorn                      │
│  Streaming          SSE via sse-starlette                 │
│  Agent Framework    LangGraph (StateGraph)                │
│  LLM Interface      LangChain + langchain-ollama          │
│  LLM Engine         Ollama (local)                        │
│  Model              qwen3:8b (8B parameters)              │
│  Medical API        PubMed E-utilities                    │
│  Storage            In-memory (VFS dict)                  │
│  State Management   MemorySaver (LangGraph)               │
└──────────────────────────────────────────────────────────┘
```

## Scaling Considerations

### Current Limitations:
- ✅ Single server
- ✅ In-memory storage (lost on restart)
- ✅ No authentication
- ✅ PubMed rate limits (3-10 req/sec)

### Production Upgrades (Template Folder):
- 🔄 PostgreSQL for persistence
- 🔄 AsyncPostgresSaver checkpointer
- 🔄 Multi-user support
- 🔄 Docker deployment
- 🔄 LangFlow integration

## File Structure Map

```
project/
├── agents/
│   ├── deep_agent.py         ← Main medical agent (StateGraph)
│   ├── medical_tools.py      ← PubMed + symptom analysis
│   ├── config.py             ← Ollama configuration
│   └── skills.py             ← Old tools (not used now)
│
├── servers/
│   ├── fastapi_server.py     ← HTTP server with /api/medical/stream
│   └── aegra_server.py       ← Alternative server (not used)
│
├── frontend/
│   ├── medical.html          ← New medical UI ⭐
│   ├── index.html            ← Old demo UI
│   └── test.html             ← SSE test page
│
├── requirements.txt          ← Python dependencies
├── run_medical.bat           ← Windows startup script
│
├── MEDICAL_SETUP.md          ← Setup instructions
├── CHANGES_SUMMARY.md        ← What changed
├── ARCHITECTURE.md           ← This file
└── QUICK_START.txt           ← Quick reference
```

## Next Steps

### Immediate (Working Now):
- ✅ PubMed search
- ✅ Doctor HITL review
- ✅ Feedback loop
- ✅ Basic tracking

### Phase 2 (RAG Integration):
- Add your RAG as fallback
- Search local medical documents
- Combine PubMed + RAG results

### Phase 3 (Advanced Learning):
- Database persistence
- Pattern analysis
- Auto-improve search strategy
- Multi-doctor support

---

**Questions about architecture?** Check MEDICAL_SETUP.md or CHANGES_SUMMARY.md
