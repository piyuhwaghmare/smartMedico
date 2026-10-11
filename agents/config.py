from langchain_ollama import ChatOllama

OLLAMA_BASE_URL = "http://localhost:11434"

# Using your downloaded models
MODEL_GENERAL = "ministral-3:3b"      # For general reasoning and medical queries
MODEL_CODE = "qwen2.5-coder:3b"       # For code generation if needed
MODEL_FAST = "qwen2.5:1.5b"           # For quick responses


def make_llm(model: str = MODEL_GENERAL, temperature: float = 0.1) -> ChatOllama:
    return ChatOllama(
        model=model,
        base_url=OLLAMA_BASE_URL,
        temperature=temperature,
    )
