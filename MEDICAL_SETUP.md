# Medical Research Agent - Setup Guide

## What Changed - Simple English Explanation

### 🎯 **Main Changes:**

1. **New Medical Agent** (`agents/medical_tools.py`)
   - Searches PubMed medical database for symptom information
   - Analyzes patient symptoms before searching
   - Summarizes findings for doctor review
   - Replaces the old "write code" and "analyze data" tools with medical-specific tools

2. **Modified Deep Agent** (`agents/deep_agent.py`)
   - Now called "Medical Agent" instead of "Deep Agent"
   - Added doctor review workflow (Human-in-the-Loop)
   - Added feedback tracking system (learns from doctor decisions)
   - When doctor rejects → agent refines search and tries again

3. **Updated Server** (`servers/fastapi_server.py`)
   - New endpoint: `/api/medical/stream` for medical queries
   - New endpoint: `/api/threads/{thread_id}/feedback` to see learning history
   - Tracks doctor Accept/Reject decisions

4. **New Medical UI** (`frontend/medical.html`)
   - Clean medical-themed interface
   - Green colors for healthcare feel
   - Shows research progress, saved files, and plan
   - Doctor review modal with Accept/Reject buttons

### 📋 **How It Works (Simple Flow):**

```
1. Patient enters symptoms → "I have headache and fever"
2. Agent analyzes symptoms → Creates research plan
3. Agent searches PubMed → Finds medical articles
4. Agent saves research → Stores in virtual file system
5. Agent summarizes findings → Prepares for doctor
6. Doctor reviews → Modal pops up with Accept/Reject
   
   If ACCEPT ✅ → Shows to patient
   If REJECT ❌ → Agent refines search and tries again (goes back to step 3)
```

### 🔧 **What You Need to Do:**

## Quick Start (Windows)

### 1. Install Dependencies

```bash
# Navigate to project folder
cd d:\System_Design\langchain-langgraph-deep-agent-patterns

# Install Python packages
pip install -r requirements.txt
```

### 2. Configure Ollama

Make sure Ollama is running with the required models:

```bash
ollama pull qwen3:8b
```

Update `agents/config.py` if your Ollama is on a different IP:
```python
OLLAMA_BASE_URL = "http://localhost:11434"  # Change this if needed
```

### 3. Optional: PubMed API Key (Recommended)

Get a free API key from: https://www.ncbi.nlm.nih.gov/account/

Set environment variable:
```bash
set PUBMED_API_KEY=your_key_here
```

**Note:** Without API key, it still works but with lower rate limits (3 requests/second vs 10/second with key)

### 4. Start the Server

```bash
# Make sure you're in the project directory
cd d:\System_Design\langchain-langgraph-deep-agent-patterns

# Start the FastAPI server
python -m uvicorn servers.fastapi_server:app --host 0.0.0.0 --port 8000 --reload
```

### 5. Open the Medical UI

Open your browser and go to:
```
http://localhost:8000/medical.html
```

You should see the Medical Research Agent interface!

## Testing It Out

### Example Patient Query:

```
I have a persistent headache for 3 days with mild fever and body ache. 
The pain is mostly on the left side of my head and gets worse in the morning.
```

### What Will Happen:

1. ✅ Agent analyzes your symptoms
2. ✅ Agent searches PubMed for relevant medical research
3. ✅ Agent saves research articles to files
4. ✅ Agent creates a summary
5. ✅ **Doctor review modal appears** with Accept/Reject buttons
6. ✅ If rejected → Agent searches again with better terms
7. ✅ If accepted → Patient sees the approved information

## Understanding the Files

### **Core Medical Files:**

- `agents/medical_tools.py` → PubMed search + symptom analysis
- `agents/deep_agent.py` → Main medical agent logic + doctor review
- `frontend/medical.html` → Patient/doctor interface
- `servers/fastapi_server.py` → HTTP server with medical endpoints

### **Key Tools Available:**

1. **analyze_symptoms** → Understands patient's problem
2. **search_medical_literature** → Searches PubMed
3. **summarize_for_doctor** → Creates doctor review summary
4. **request_doctor_review** → Pauses for doctor decision
5. **refine_search_with_feedback** → Improves search after rejection

## Learning System (Simple Version)

The agent tracks every doctor decision in memory:
- Stores: timestamp, Accept/Reject, research summary snippet
- Use `/api/threads/{thread_id}/feedback` to see history
- **Future:** Can analyze patterns to learn what doctors prefer

## Next Steps (What We'll Add Later)

### Phase 2 - RAG Integration:
1. You give me your RAG implementation
2. I'll add it as a fallback when PubMed doesn't find good results
3. Upload medical PDF documents → Agent searches them first

### Phase 3 - Better Learning:
1. Save feedback to database (not just memory)
2. Analyze patterns: "Doctor always rejects outdated studies"
3. Use patterns to improve future searches automatically

### Phase 4 - Improvements:
1. Add doctor login/authentication
2. Multi-doctor review tracking
3. Patient history tracking
4. Export approved reports as PDF

## Troubleshooting

### ❌ "Connection refused" error:
- Make sure Ollama is running
- Check `OLLAMA_BASE_URL` in `agents/config.py`

### ❌ "PubMed API rate limit":
- Get free API key (see step 3 above)
- Reduce search frequency

### ❌ Doctor review modal not showing:
- Check browser console (F12) for errors
- Make sure server is running
- Try refreshing the page

### ❌ Agent not finding articles:
- Try more medical terminology
- Example: Instead of "head pain" → "headache" or "cephalalgia"
- PubMed prefers medical terms

## File Structure After Changes

```
d:\System_Design\langchain-langgraph-deep-agent-patterns\
├── agents/
│   ├── config.py              (unchanged - Ollama config)
│   ├── deep_agent.py          (MODIFIED - now medical agent)
│   ├── medical_tools.py       (NEW - PubMed search tools)
│   ├── simple_agent.py        (unchanged - not used)
│   └── skills.py              (unchanged - not used now)
├── servers/
│   ├── fastapi_server.py      (MODIFIED - added medical endpoint)
│   └── aegra_server.py        (unchanged)
├── frontend/
│   ├── index.html             (unchanged - old UI)
│   ├── medical.html           (NEW - medical UI)
│   └── test.html              (unchanged)
├── requirements.txt           (MODIFIED - added 'requests')
├── README.md                  (MODIFIED - new description)
└── MEDICAL_SETUP.md           (NEW - this file)
```

## Questions?

If something doesn't work or you need clarification, let me know:

1. Which step failed?
2. What error message did you see?
3. What were you trying to do?

I'll help you fix it! 🚀
