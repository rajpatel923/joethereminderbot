import os

from langchain_openai import ChatOpenAI


def get_llm_config(provider: str) -> tuple[str, str, str]:
    """Returns (base_url, api_key, model_name) for the given provider."""
    if provider == "vllm":
        base_url = os.environ.get("VLLM_BASE_URL")
        if not base_url:
            raise ValueError("LLM_PROVIDER=vllm requires VLLM_BASE_URL to be set")
        model_name = os.environ.get("VLLM_MODEL_NAME")
        if not model_name:
            raise ValueError("LLM_PROVIDER=vllm requires VLLM_MODEL_NAME to be set")
        return base_url, "none", model_name

    elif provider == "ollama":
        base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        model_name = os.environ.get("OLLAMA_MODEL_NAME")
        if not model_name:
            raise ValueError("LLM_PROVIDER=ollama requires OLLAMA_MODEL_NAME to be set")
        return base_url, "ollama", model_name

    elif provider == "openrouter":
        base_url = "https://openrouter.ai/api/v1"
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("LLM_PROVIDER=openrouter requires OPENROUTER_API_KEY to be set")
        model_name = os.environ.get("OPENROUTER_MODEL_NAME")
        if not model_name:
            raise ValueError("LLM_PROVIDER=openrouter requires OPENROUTER_MODEL_NAME to be set")
        return base_url, api_key, model_name

    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER '{provider}'. Must be one of: vllm, ollama, openrouter"
        )


def make_llm(provider: str) -> ChatOpenAI:
    """Returns a ChatOpenAI instance configured for the given provider."""
    base_url, api_key, model_name = get_llm_config(provider)
    kwargs = {}
    if provider == "ollama":
        # Disable thinking mode for Qwen3-family models — thinking tokens
        # are inserted before tool calls and break Ollama's tool-call parsing.
        kwargs["model_kwargs"] = {"options": {"num_ctx": 8192}, "think": False}
    return ChatOpenAI(base_url=base_url, api_key=api_key, model=model_name, **kwargs)
