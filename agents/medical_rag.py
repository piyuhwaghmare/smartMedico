"""
Medical RAG Agent - Proper Retrieval-Augmented Generation Pipeline

Pipeline:
1. Search multiple sources (PubMed, Wikipedia, DuckDuckGo)
2. Store documents in ChromaDB vector database
3. Retrieve most relevant chunks using embeddings
4. Feed to Ollama LLM (ministral-3:3b) for synthesis
5. Doctor approves LLM-generated summary
6. Show to patient
"""

import os
import requests
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Annotated, Any, List
import uuid

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt
from typing_extensions import TypedDict

from .config import make_llm, MODEL_GENERAL

# ── Configuration ─────────────────────────────────────────────────────────────

PUBMED_API_KEY = "7642a82d5f430265d302cde5a5a106a0a808"
PUBMED_SEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_FETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# Initialize embedding model (lightweight)
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')  # 80MB model, fast

# Initialize ChromaDB (persistent storage)
chroma_client = chromadb.Client(Settings(
    persist_directory="./chroma_db",
    anonymized_telemetry=False
))

# Thread-scoped storage
_search_results: dict[str, list] = defaultdict(list)
_approved_results: dict[str, list] = defaultdict(list)
_feedback_history: dict[str, list] = defaultdict(list)


# ── State ─────────────────────────────────────────────────────────────────────

class MedicalRAGState(TypedDict):
    messages: Annotated[list, add_messages]
    query: str
    raw_documents: List[dict]
    llm_summary: str
    search_done: bool
    synthesis_done: bool


# ── Step 1: Multi-Source Search ──────────────────────────────────────────────

def search_pubmed(query: str, max_results: int = 5) -> List[dict]:
    """Search PubMed and return full articles with abstracts"""
    print(f"[PubMed] Searching for: {query}")
    try:
        # Search for IDs
        search_params = {
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retmode": "json",
            "api_key": PUBMED_API_KEY,
            "sort": "relevance"
        }
        
        print(f"[PubMed] Making search request...")
        search_response = requests.get(PUBMED_SEARCH_URL, params=search_params, timeout=10)
        search_response.raise_for_status()
        id_list = search_response.json().get("esearchresult", {}).get("idlist", [])
        
        print(f"[PubMed] Found {len(id_list)} article IDs")
        
        if not id_list:
            print("[PubMed] No articles found")
            return []
        
        # Fetch full articles with abstracts
        fetch_params = {
            "db": "pubmed",
            "id": ",".join(id_list),
            "retmode": "xml",
            "api_key": PUBMED_API_KEY
        }
        
        print(f"[PubMed] Fetching full articles...")
        fetch_response = requests.get(PUBMED_FETCH_URL, params=fetch_params, timeout=15)
        fetch_response.raise_for_status()
        
        root = ET.fromstring(fetch_response.content)
        results = []
        
        for article in root.findall(".//PubmedArticle"):
            pmid = article.find(".//PMID")
            title = article.find(".//ArticleTitle")
            abstract_parts = article.findall(".//AbstractText")
            abstract = " ".join([p.text for p in abstract_parts if p.text]) if abstract_parts else ""
            
            if pmid is not None and title is not None and abstract:
                results.append({
                    "source": "PubMed",
                    "pmid": pmid.text,
                    "title": title.text,
                    "content": abstract,
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid.text}"
                })
        
        print(f"[PubMed] Successfully parsed {len(results)} articles")
        return results
    except Exception as e:
        print(f"[PubMed] ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return []


def search_wikipedia(query: str) -> List[dict]:
    """Search Wikipedia for medical information"""
    print(f"[Wikipedia] Searching for: {query}")
    try:
        import wikipedia
        
        # Set user agent to avoid API issues
        wikipedia.set_user_agent("MedicalAgent/1.0 (piyush.waghmare142@gmail.com)")
        
        # Search for relevant pages
        search_results = wikipedia.search(query, results=3)
        print(f"[Wikipedia] Found {len(search_results)} pages")
        
        docs = []
        for title in search_results:
            try:
                page = wikipedia.page(title, auto_suggest=False)
                content = page.content[:1000]
                docs.append({
                    "source": "Wikipedia",
                    "title": title,
                    "content": content,
                    "url": page.url
                })
                print(f"[Wikipedia] Added: {title}")
            except Exception as e:
                print(f"[Wikipedia] Skipped {title}: {e}")
                continue
        
        print(f"[Wikipedia] Got {len(docs)} documents")
        return docs
    except Exception as e:
        print(f"[Wikipedia] ERROR: {e}")
        import traceback
        traceback.print_exc()
        return []


def search_web(query: str) -> List[dict]:
    """Search web using DuckDuckGo"""
    try:
        from duckduckgo_search import DDGS
        
        results = []
        ddgs = DDGS()
        search_results = ddgs.text(query + " medical", max_results=3)
        
        for r in search_results:
            results.append({
                "source": "Web",
                "title": r.get("title", ""),
                "content": r.get("body", ""),
                "url": r.get("href", "")
            })
        
        return results
    except Exception as e:
        print(f"Web search error: {e}")
        return []


# ── Step 2: Store in Vector DB ───────────────────────────────────────────────

def store_in_vectordb(documents: List[dict], collection_name: str) -> chromadb.Collection:
    """Store documents in ChromaDB with embeddings"""
    
    # Create or get collection
    try:
        collection = chroma_client.get_collection(collection_name)
        chroma_client.delete_collection(collection_name)  # Clear old data
    except:
        pass
    
    collection = chroma_client.create_collection(
        name=collection_name,
        metadata={"description": "Medical research documents"}
    )
    
    # Prepare documents
    ids = []
    texts = []
    metadatas = []
    
    for i, doc in enumerate(documents):
        doc_id = f"{doc['source']}_{i}_{uuid.uuid4().hex[:8]}"
        text = f"{doc['title']}\n\n{doc['content']}"
        
        ids.append(doc_id)
        texts.append(text)
        metadatas.append({
            "source": doc["source"],
            "title": doc["title"],
            "url": doc.get("url", "")
        })
    
    # Generate embeddings and store
    if texts:
        embeddings = embedding_model.encode(texts).tolist()
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas
        )
    
    return collection


# ── Step 3: Retrieve Relevant Context ────────────────────────────────────────

def retrieve_context(query: str, collection: chromadb.Collection, top_k: int = 5) -> str:
    """Retrieve most relevant documents from vector DB"""
    
    # Generate query embedding
    query_embedding = embedding_model.encode([query])[0].tolist()
    
    # Search vector DB
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k
    )
    
    # Format context
    context = "=== RELEVANT MEDICAL INFORMATION ===\n\n"
    
    for i, (doc, meta) in enumerate(zip(results['documents'][0], results['metadatas'][0])):
        context += f"Source {i+1} ({meta['source']} - {meta['title']}):\n"
        context += f"{doc}\n"
        context += f"URL: {meta['url']}\n\n"
        context += "---\n\n"
    
    return context


# ── Step 4: LLM Synthesis ────────────────────────────────────────────────────

def synthesize_with_llm(query: str, context: str) -> str:
    """Use LLM to generate medical summary from retrieved context"""
    
    # Limit context size to avoid Gemini BadRequestError (max ~30k tokens)
    # Each token is ~4 chars, so limit to ~60k chars to be safe
    if len(context) > 60000:
        print(f"[LLM] Context too large ({len(context)} chars), truncating to 60k chars")
        context = context[:60000] + "\n\n[Context truncated due to length...]"
    
    system_prompt = """You are a medical information assistant. Your job is to:

1. Analyze the provided medical research context
2. Extract key information relevant to the patient's query
3. Synthesize a clear, accurate, evidence-based summary
4. Cite sources (mention PubMed PMIDs, Wikipedia, etc.)
5. Include: possible causes, symptoms, when to see a doctor, general guidance

IMPORTANT:
- Be factual and evidence-based
- Cite your sources
- Recommend seeing a healthcare provider for diagnosis
- Do NOT provide specific medical advice or diagnoses
- Keep response under 500 words"""

    user_prompt = f"""Patient Query: {query}

Retrieved Medical Context:
{context}

Please synthesize this information into a helpful, clear summary for the patient."""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt)
    ]
    
    # Try Gemini first
    try:
        print(f"[LLM] Attempting synthesis with Gemini (context: {len(context)} chars)...")
        llm = make_llm(MODEL_GENERAL, temperature=0.2, use_azure=True)
        response = llm.invoke(messages)
        content = response.content
        
        if content and len(content) >= 50:
            print(f"[LLM] ✅ Gemini generated {len(content)} character summary")
            return content
        else:
            raise ValueError("Gemini response too short or empty")
            
    except Exception as Gemini_error:
        error_msg = str(Gemini_error)
        print(f"[LLM] ⚠️ Gemini failed: {type(Gemini_error).__name__}: {error_msg[:200]}")
        
        # If BadRequestError, context might be too large even after truncation
        if "BadRequestError" in type(Gemini_error).__name__ or "400" in error_msg:
            print(f"[LLM] BadRequestError detected - trying with smaller context...")
            # Try again with much smaller context (first 20k chars only)
            smaller_context = context[:20000] + "\n\n[Truncated for API limits...]"
            smaller_prompt = f"""Patient Query: {query}

Retrieved Medical Context (truncated):
{smaller_context}

Please synthesize this information into a helpful, clear summary for the patient."""
            
            try:
                messages = [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=smaller_prompt)
                ]
                response = llm.invoke(messages)
                content = response.content
                if content and len(content) >= 50:
                    print(f"[LLM] ✅ Gemini succeeded with smaller context")
                    return content
            except Exception as retry_error:
                print(f"[LLM] Gemini still failed with smaller context: {retry_error}")
        
        print(f"[LLM] Falling back to Ollama...")
        
        # Try Ollama fallback
        try:
            llm = make_llm(MODEL_GENERAL, temperature=0.2, use_azure=True)
            response = llm.invoke(messages)
            content = response.content
            
            if content and len(content) >= 50:
                print(f"[LLM] ✅ Ollama generated {len(content)} character summary")
                return content
            else:
                raise ValueError("Ollama response too short or empty")
                
        except Exception as ollama_error:
            print(f"[LLM] ❌ Ollama also failed: {type(ollama_error).__name__}: {str(ollama_error)[:200]}")
            
            # Both failed - return context with instructions
            return f"""⚠️ **LLM Synthesis Failed**

I successfully retrieved medical information from {len(context.split('Source'))-1} sources, but both Gemini and Ollama failed to generate a summary.

**Gemini Error:** {type(Gemini_error).__name__} - {str(Gemini_error)[:100]}
**Ollama Error:** {type(ollama_error).__name__}

**Here's the raw medical information I found:**

{context[:2000]}...

**Possible causes of this error:**
1. **Context too large:** The retrieved information exceeded API limits
2. **Ollama not running:** Make sure Ollama is running: `ollama serve`
3. **Model not downloaded:** Run `ollama pull ministral-3:3b`

**What you can do:**
- Try a more specific query (e.g., "tension headache" instead of "headache")
- Restart Ollama and try again
- Review the raw context above for immediate information"""


# ── Graph Nodes ───────────────────────────────────────────────────────────────

def search_node(state: MedicalRAGState, config: RunnableConfig) -> dict:
    """Search multiple sources and collect documents"""
    thread_id = config.get("configurable", {}).get("thread_id", "default")
    query = state["query"]
    
    print(f"[SEARCH] Searching for: {query}")
    
    # Search all sources
    pubmed_docs = search_pubmed(query, max_results=3)
    wiki_docs = search_wikipedia(query)
    web_docs = search_web(query)
    
    all_docs = pubmed_docs + wiki_docs + web_docs
    
    print(f"[SEARCH] Found {len(all_docs)} documents (PubMed: {len(pubmed_docs)}, Wiki: {len(wiki_docs)}, Web: {len(web_docs)})")
    
    _search_results[thread_id] = all_docs
    
    if not all_docs:
        return {
            "messages": [AIMessage(content="❌ No information found. Please rephrase your query.")],
            "raw_documents": [],
            "search_done": True,
            "synthesis_done": True
        }
    
    summary_msg = f"🔍 **Searching medical sources...**\n\n"
    summary_msg += f"✅ Found {len(pubmed_docs)} PubMed articles\n"
    summary_msg += f"✅ Found {len(wiki_docs)} Wikipedia pages\n"
    summary_msg += f"✅ Found {len(web_docs)} web sources\n\n"
    summary_msg += "📊 **Building knowledge base...**"
    
    return {
        "messages": [AIMessage(content=summary_msg)],
        "raw_documents": all_docs,
        "search_done": True,
    }


def synthesize_node(state: MedicalRAGState, config: RunnableConfig) -> dict:
    """Store in vector DB, retrieve context, and synthesize with LLM"""
    thread_id = config.get("configurable", {}).get("thread_id", "default")
    query = state["query"]
    documents = state["raw_documents"]
    
    print(f"[SYNTHESIZE] Processing {len(documents)} documents")
    
    # Store in vector DB
    collection_name = f"medical_{thread_id}"
    collection = store_in_vectordb(documents, collection_name)
    
    # Retrieve relevant context
    context = retrieve_context(query, collection, top_k=5)
    
    print(f"[SYNTHESIZE] Retrieved context, calling LLM...")
    
    # Synthesize with LLM
    llm_summary = synthesize_with_llm(query, context)
    
    print(f"[SYNTHESIZE] LLM generated {len(llm_summary)} chars")
    
    msg = "🤖 **AI Analysis Complete**\n\n" + llm_summary + "\n\n⏳ **Sending to doctor for approval...**"
    
    return {
        "messages": [AIMessage(content=msg)],
        "llm_summary": llm_summary,
        "synthesis_done": True,
    }


def approval_node(state: MedicalRAGState, config: RunnableConfig) -> dict:
    """Request doctor approval for LLM-generated summary"""
    thread_id = config.get("configurable", {}).get("thread_id", "default")
    
    llm_summary = state.get("llm_summary", "")
    query = state["query"]
    
    print(f"[APPROVAL] Requesting doctor review")
    
    if not llm_summary:
        return {
            "messages": [AIMessage(content="⚠️ No summary generated for approval.")],
        }
    
    approval_data = {
        "question": f"🩺 **Doctor Review Required**\n\nPatient Query: *'{query}'*\n\nAI has analyzed multiple medical sources and generated this summary. Please review:",
        "findings": llm_summary,
        "sources": f"{len(state.get('raw_documents', []))} sources analyzed",
        "options": [
            "✅ Approve - Information is accurate",
            "❌ Reject - Needs improvement",
            "⚠️ Reject - Incorrect information"
        ]
    }
    
    # Pause for doctor
    choice = interrupt(approval_data)
    
    print(f"[APPROVAL] Doctor chose: {choice}")
    
    if "Approve" in choice:
        _approved_results[thread_id].append({
            "summary": llm_summary,
            "status": "approved"
        })
        
        msg = "✅ **DOCTOR APPROVED**\n\n" + llm_summary + "\n\n⚕️ *Reviewed and approved by a medical professional.*"
        return {"messages": [AIMessage(content=msg)]}
    else:
        feedback = choice.split("-")[1].strip() if "-" in choice else "rejected"
        return {"messages": [AIMessage(content=f"❌ Doctor feedback: {feedback}")]}


# ── Graph ─────────────────────────────────────────────────────────────────────

def create_medical_rag_agent():
    """Create RAG-powered medical agent"""
    
    graph = StateGraph(MedicalRAGState)
    
    graph.add_node("search", search_node)
    graph.add_node("synthesize", synthesize_node)
    graph.add_node("approve", approval_node)
    
    graph.set_entry_point("search")
    graph.add_edge("search", "synthesize")
    graph.add_edge("synthesize", "approve")
    graph.add_edge("approve", END)
    
    memory = MemorySaver()
    return graph.compile(checkpointer=memory)


# Export
def get_search_results(thread_id: str) -> list:
    return list(_search_results.get(thread_id, []))


def get_approved_results(thread_id: str) -> list:
    return list(_approved_results.get(thread_id, []))


def get_feedback_history(thread_id: str) -> list:
    return list(_feedback_history.get(thread_id, []))


MEDICAL_AGENT = create_medical_rag_agent()




