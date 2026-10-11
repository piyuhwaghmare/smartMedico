"""
Medical research tools for searching PubMed and medical databases.
"""

import os
import requests
from typing import Optional
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

# PubMed API configuration
PUBMED_API_KEY = os.getenv("PUBMED_API_KEY", "")  # Optional, but increases rate limits
PUBMED_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def search_pubmed(query: str, max_results: int = 5) -> list[dict]:
    """
    Search PubMed for medical articles related to the query.
    Returns list of articles with title, abstract, and PMID.
    """
    try:
        # Step 1: Search for article IDs
        search_url = f"{PUBMED_BASE_URL}/esearch.fcgi"
        search_params = {
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retmode": "json",
            "sort": "relevance",
        }
        if PUBMED_API_KEY:
            search_params["api_key"] = PUBMED_API_KEY
        
        search_response = requests.get(search_url, params=search_params, timeout=10)
        search_response.raise_for_status()
        search_data = search_response.json()
        
        id_list = search_data.get("esearchresult", {}).get("idlist", [])
        if not id_list:
            return []
        
        # Step 2: Fetch article details
        fetch_url = f"{PUBMED_BASE_URL}/efetch.fcgi"
        fetch_params = {
            "db": "pubmed",
            "id": ",".join(id_list),
            "retmode": "xml",
        }
        if PUBMED_API_KEY:
            fetch_params["api_key"] = PUBMED_API_KEY
        
        fetch_response = requests.get(fetch_url, params=fetch_params, timeout=15)
        fetch_response.raise_for_status()
        
        # Parse XML response (simplified parsing)
        articles = []
        xml_content = fetch_response.text
        
        # Simple extraction - split by article tags
        import re
        article_blocks = re.findall(r'<PubmedArticle>(.*?)</PubmedArticle>', xml_content, re.DOTALL)
        
        for block in article_blocks[:max_results]:
            # Extract PMID
            pmid_match = re.search(r'<PMID[^>]*>(.*?)</PMID>', block)
            pmid = pmid_match.group(1) if pmid_match else "Unknown"
            
            # Extract title
            title_match = re.search(r'<ArticleTitle>(.*?)</ArticleTitle>', block)
            title = title_match.group(1) if title_match else "No title"
            title = re.sub(r'<[^>]+>', '', title)  # Remove any HTML tags
            
            # Extract abstract
            abstract_match = re.search(r'<AbstractText[^>]*>(.*?)</AbstractText>', block, re.DOTALL)
            abstract = abstract_match.group(1) if abstract_match else "No abstract available"
            abstract = re.sub(r'<[^>]+>', '', abstract)  # Remove any HTML tags
            abstract = abstract[:500] + "..." if len(abstract) > 500 else abstract
            
            # Extract publication year
            year_match = re.search(r'<PubDate>.*?<Year>(.*?)</Year>', block, re.DOTALL)
            year = year_match.group(1) if year_match else "Unknown"
            
            articles.append({
                "pmid": pmid,
                "title": title,
                "abstract": abstract,
                "year": year,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            })
        
        return articles
    
    except Exception as e:
        print(f"[PubMed Error] {e}")
        return []


@tool
def search_medical_literature(query: str, max_results: int = 5) -> str:
    """
    Search PubMed medical database for information about symptoms, diseases, or treatments.
    Returns relevant medical research articles.
    
    Args:
        query: Medical query (symptoms, disease names, treatment information)
        max_results: Maximum number of articles to return (default 5)
    """
    articles = search_pubmed(query, max_results)
    
    if not articles:
        return f"No PubMed articles found for query: '{query}'. Try rephrasing or using medical terminology."
    
    result = f"Found {len(articles)} relevant PubMed articles for '{query}':\n\n"
    
    for i, article in enumerate(articles, 1):
        result += f"{i}. {article['title']} ({article['year']})\n"
        result += f"   PMID: {article['pmid']}\n"
        result += f"   Abstract: {article['abstract']}\n"
        result += f"   URL: {article['url']}\n\n"
    
    return result


@tool
def analyze_symptoms(symptoms: str, config: RunnableConfig) -> str:
    """
    Analyze the provided symptoms and create a structured medical research plan.
    This should be called FIRST before searching for information.
    
    Args:
        symptoms: Patient's symptoms and problems described in natural language
    """
    from .config import make_llm, MODEL_GENERAL
    from langchain_core.messages import SystemMessage, HumanMessage
    
    llm = make_llm(MODEL_GENERAL)
    
    response = llm.invoke([
        SystemMessage(content=(
            "You are a medical research assistant. Given patient symptoms, "
            "create a structured analysis:\n"
            "1. List the key symptoms mentioned\n"
            "2. Identify potential medical conditions to research\n"
            "3. Suggest specific medical search terms for PubMed\n"
            "Be concise and use proper medical terminology."
        )),
        HumanMessage(content=f"Patient symptoms/problems:\n{symptoms}")
    ])
    
    return f"[SYMPTOM ANALYSIS]\n{response.content}"


@tool
def summarize_for_doctor(research_findings: str) -> str:
    """
    Summarize medical research findings in a clear format for doctor review.
    Highlights key information, evidence quality, and recommendations.
    
    Args:
        research_findings: Raw research information from PubMed searches
    """
    from .config import make_llm, MODEL_GENERAL
    from langchain_core.messages import SystemMessage, HumanMessage
    
    llm = make_llm(MODEL_GENERAL)
    
    response = llm.invoke([
        SystemMessage(content=(
            "You are a medical research summarizer. Create a clear, structured summary "
            "for doctor review:\n"
            "1. KEY FINDINGS: Main medical insights\n"
            "2. EVIDENCE QUALITY: Strength of research (recent studies, sample sizes)\n"
            "3. CLINICAL RELEVANCE: How this applies to the patient\n"
            "4. RECOMMENDATIONS: Suggested next steps\n"
            "Be objective and cite PMIDs when available."
        )),
        HumanMessage(content=f"Research findings:\n\n{research_findings}")
    ])
    
    return f"[MEDICAL SUMMARY FOR DOCTOR REVIEW]\n{response.content}"
