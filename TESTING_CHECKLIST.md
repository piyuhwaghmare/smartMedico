# Testing Checklist - Medical Research Agent

Use this checklist to verify everything is working correctly.

## ✅ Pre-Testing Setup

- [ ] **Ollama is running**
  ```bash
  # Check if Ollama is running
  curl http://localhost:11434/api/tags
  ```
  Should return list of models (not error)

- [ ] **Model is downloaded**
  ```bash
  ollama list
  ```
  Should show `qwen3:8b` in the list

- [ ] **Dependencies installed**
  ```bash
  pip list | findstr langchain
  pip list | findstr fastapi
  ```
  Should show langchain, langgraph, fastapi packages

## ✅ Server Testing

### Test 1: Server Starts
```bash
cd d:\System_Design\langchain-langgraph-deep-agent-patterns
python -m uvicorn servers.fastapi_server:app --port 8000
```

**Expected:** 
- ✅ No errors
- ✅ Shows "Uvicorn running on http://0.0.0.0:8000"
- ✅ "Application startup complete"

### Test 2: API is Accessible
Open browser to: `http://localhost:8000/docs`

**Expected:**
- ✅ Swagger UI loads
- ✅ Shows endpoints like `/api/medical/stream`
- ✅ No 404 or 500 errors

### Test 3: Medical UI Loads
Open browser to: `http://localhost:8000/`

**Expected:**
- ✅ Medical UI displays (green theme, healthcare design)
- ✅ Shows "Medical Research Agent" title
- ✅ Input textarea is visible
- ✅ Example prompts are clickable
- ✅ Sidebar shows "Research Status"

## ✅ Basic Functionality Tests

### Test 4: Simple Symptom Query

**Input:**
```
I have a headache
```

**Expected:**
1. ✅ Message appears in chat as "Patient Query"
2. ✅ Agent message starts appearing with "🤖 Medical Agent"
3. ✅ Tool executions show:
   - ⚙️ analyze_symptoms (running → completed)
   - ⚙️ search_medical_literature (running → completed)
   - ⚙️ summarize_for_doctor (running → completed)
4. ✅ Research plan appears in sidebar (todos)
5. ✅ Agent stops and waits (no more streaming)

**If any tool fails:**
- Check Ollama connection
- Check terminal for errors
- Verify model is loaded: `ollama list`

### Test 5: Doctor Review Modal

**Continuing from Test 4...**

**Expected:**
- ✅ Modal pops up with "👨‍⚕️ Doctor Review Required"
- ✅ Shows summary of research findings
- ✅ Two buttons visible:
  - ✅ "Accept - Approve for patient" (green)
  - ❌ "Reject - Request refinement"

**Test Accept:**
- Click "Accept" button
- ✅ Modal closes
- ✅ Agent continues with acceptance message
- ✅ Shows approved information to patient

### Test 6: Reject and Refine

**Input a new query:**
```
I have chest pain
```

**Wait for doctor review modal, then:**
1. Click "Reject - Request refinement"
2. Enter feedback: "Need more recent studies from 2023-2024"
3. Click OK

**Expected:**
1. ✅ Modal closes
2. ✅ Agent acknowledges rejection
3. ✅ Tool: refine_search_with_feedback runs
4. ✅ Tool: search_medical_literature runs AGAIN (with refinement)
5. ✅ NEW research findings appear
6. ✅ Doctor review modal appears AGAIN with new findings

## ✅ PubMed Integration Tests

### Test 7: PubMed API Connectivity

**Input:**
```
migraine with aura symptoms
```

**Expected:**
1. ✅ search_medical_literature tool runs
2. ✅ Tool output shows:
   - "Found X relevant PubMed articles"
   - PMID numbers (e.g., "PMID: 12345678")
   - Article titles
   - Abstracts (partial)
   - Years (should be recent)
   - URLs to pubmed.ncbi.nlm.nih.gov

**If PubMed fails:**
- Check internet connection
- Check error in terminal
- Try with API key: `set PUBMED_API_KEY=your_key`

### Test 8: No Results Handling

**Input:**
```
xyzabc123 fake symptom that does not exist
```

**Expected:**
- ✅ search_medical_literature runs
- ✅ Returns: "No PubMed articles found"
- ✅ Agent handles gracefully (doesn't crash)
- ✅ Agent may suggest rephrasing or using medical terms

## ✅ File Storage Tests

### Test 9: VFS File Creation

**Input any medical query, then check sidebar**

**Expected:**
- ✅ "Saved Research" section shows files
- ✅ Files have names like:
  - `research_headache.txt`
  - `pubmed_results.txt`
  - `summary.txt`
- ✅ File names are visible in sidebar

### Test 10: API File Access

**Get thread ID from network tab (F12 → Network), then:**

```bash
curl http://localhost:8000/api/threads/YOUR_THREAD_ID/vfs
```

**Expected:**
- ✅ Returns JSON with files object
- ✅ Each file has path and content
- ✅ Content contains research information

## ✅ Learning System Tests

### Test 11: Feedback Tracking

**After completing Test 5 (Accept) and Test 6 (Reject):**

```bash
curl http://localhost:8000/api/threads/YOUR_THREAD_ID/feedback
```

**Expected:**
- ✅ Returns JSON with feedback_history array
- ✅ Contains at least 2 entries:
  - One with "Accept" decision
  - One with "Reject" decision
- ✅ Each entry has: timestamp, decision, summary

### Test 12: Multi-Query Learning

**Run 3 different queries in same thread:**
1. "headache" → Accept
2. "fever" → Reject with feedback
3. "chest pain" → Accept

**Check feedback:**
```bash
curl http://localhost:8000/api/threads/YOUR_THREAD_ID/feedback
```

**Expected:**
- ✅ Shows 3 entries
- ✅ All timestamped
- ✅ Mix of Accept and Reject
- ✅ Feedback text is stored

## ✅ Error Handling Tests

### Test 13: Empty Input

**Action:** Click "Research" button with empty textarea

**Expected:**
- ✅ Button is disabled (can't click)
- OR
- ✅ Shows error message "Please enter symptoms"

### Test 14: Ollama Down

**Action:** 
1. Stop Ollama service
2. Try to send a query

**Expected:**
- ✅ Shows error message in chat
- ✅ Error mentions connection issue
- ✅ UI doesn't freeze or crash

### Test 15: Very Long Input

**Input:**
```
[Paste 500 words of random medical symptoms]
```

**Expected:**
- ✅ Accepts input
- ✅ Processes normally
- ✅ May take longer but doesn't crash
- ✅ Results are still coherent

## ✅ UI/UX Tests

### Test 16: Responsive Sidebar

**Action:** Enter query and watch sidebar

**Expected:**
- ✅ Research plan (todos) updates in real-time
- ✅ Saved files list updates when files are created
- ✅ Updates happen DURING agent execution (not just at end)

### Test 17: Message Scrolling

**Action:** Send 5-10 queries in a row

**Expected:**
- ✅ Chat auto-scrolls to bottom
- ✅ New messages always visible
- ✅ No need to manually scroll

### Test 18: Keyboard Shortcuts

**Action:** 
1. Type in textarea
2. Press `Enter` (not Shift+Enter)

**Expected:**
- ✅ Sends message
- ✅ Same as clicking "Research" button

**Action:**
1. Type in textarea
2. Press `Shift+Enter`

**Expected:**
- ✅ Creates new line
- ✅ Does NOT send message

## ✅ Performance Tests

### Test 19: Response Time

**Input:** "I have a headache"

**Measure time from send to first AI token:**

**Expected:**
- ✅ First token arrives within 5 seconds
- ✅ Streaming is smooth (no long pauses)
- ✅ PubMed search completes within 10 seconds

### Test 20: Concurrent Queries

**Action:** Open 2 browser tabs, send queries simultaneously

**Expected:**
- ✅ Both queries process
- ✅ No interference between tabs
- ✅ Each has own thread_id
- ✅ Results don't mix

## ✅ Edge Cases

### Test 21: Special Characters

**Input:**
```
I have pain in my chest & arms (left side) - sharp, 10/10 severity!!!
```

**Expected:**
- ✅ Processes normally
- ✅ Special characters don't break anything
- ✅ Results are relevant

### Test 22: Non-English Input

**Input:**
```
J'ai mal à la tête depuis 3 jours
```

**Expected:**
- ✅ Agent tries to process
- ✅ May suggest using English
- ✅ Doesn't crash

### Test 23: Modal Dismiss

**Action:** 
1. Trigger doctor review modal
2. Click outside modal (on dark overlay)

**Expected:**
- ✅ Modal stays open (doesn't dismiss accidentally)
- OR
- ✅ If dismisses, agent handles it gracefully

## 📊 Test Results Summary

After running all tests, fill this out:

```
Total Tests: 23
Passed: ___
Failed: ___

Failed Tests (list numbers):
_________________________________
_________________________________

Critical Issues:
_________________________________
_________________________________

Minor Issues:
_________________________________
_________________________________
```

## 🐛 Common Issues & Fixes

### Issue: "Connection refused" error
**Fix:** Check Ollama is running: `curl http://localhost:11434/api/tags`

### Issue: "Model not found" error
**Fix:** Download model: `ollama pull qwen3:8b`

### Issue: PubMed returns no results
**Fix:** 
1. Check internet connection
2. Try simpler medical terms
3. Check terminal for API errors

### Issue: Modal doesn't appear
**Fix:**
1. Open browser console (F12)
2. Check for JavaScript errors
3. Look for "interrupt" event in Network tab
4. Verify agent reaches request_doctor_review tool

### Issue: Slow response
**Fix:**
1. Check Ollama performance: `ollama ps`
2. Reduce model size if needed
3. Check CPU/GPU usage
4. May need better hardware for faster responses

## 🚀 Next: Report Results

After testing, share:
1. Which tests passed ✅
2. Which tests failed ❌
3. Any error messages you saw
4. Screenshots of issues (if any)

Then we can:
- Fix any problems
- Add RAG integration
- Improve learning system
- Add more features

---

**Good luck with testing! 🧪**
