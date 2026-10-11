import os
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# Models
MODEL_GENERAL = "qwen2:0.5b"  # Ollama fallback


def make_llm(model: str = MODEL_GENERAL, temperature: float = 0.1, use_azure: bool = True):
    """Use Azure OpenAI via GitHub token (FAST) with Ollama fallback"""
    
    if use_azure and GITHUB_TOKEN:
        try:
            print(f"[LLM] Using Azure OpenAI (GitHub Models) - gpt-4o-mini")
            return ChatOpenAI(
                model="gpt-4o-mini",
                api_key=GITHUB_TOKEN,
                base_url="https://models.inference.ai.azure.com",
                temperature=temperature,
                timeout=30,
            )
        except Exception as e:
            print(f"[LLM] ⚠️ Azure failed: {e}")
            print(f"[LLM] Falling back to Ollama")
    
    # Fallback to Ollama
    print(f"[LLM] Using Ollama - model: {model}")
    return ChatOllama(
        model=model,
        base_url=OLLAMA_BASE_URL,
        temperature=temperature,
        timeout=120,
    )
