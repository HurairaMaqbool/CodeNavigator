# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/evaluation/ragas_providers.py
---------------------------------
Free-provider overrides for RAGAS.

CRITICAL SECURITY & COST NOTE:
RAGAS defaults to OpenAI for both the judge LLM and embeddings. If left
unconfigured, it silently makes paid API calls.
This module overrides the RAGAS wrappers using exactly the providers and models
specified in `app/config.py`. 
"""
from __future__ import annotations

from typing import Any

from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from langchain_huggingface import HuggingFaceEmbeddings

from app.config import settings
from app.observability.logging_config import logger

def get_judge_embeddings() -> LangchainEmbeddingsWrapper:
    """Uses the same free local embedding model as the main pipeline."""
    # We load it into Langchain's wrapper
    embeddings = HuggingFaceEmbeddings(model_name=settings.EMBEDDING_MODEL)
    return LangchainEmbeddingsWrapper(embeddings)

def get_judge_llm() -> LangchainLLMWrapper:
    """
    Returns the appropriate Langchain-wrapped LLM based on LLM_PROVIDER.
    Fails loudly if not properly configured to prevent silent fallback to OpenAI.
    """
    if settings.LLM_PROVIDER == "groq":
        from langchain_groq import ChatGroq
        if not settings.GROQ_API_KEY:
            raise ValueError(
                "GROQ_API_KEY is not set but LLM_PROVIDER is 'groq'. "
                "Refusing to fall back to OpenAI."
            )
        llm = ChatGroq(model=settings.LLM_MODEL, groq_api_key=settings.GROQ_API_KEY)
        return LangchainLLMWrapper(llm)
        
    elif settings.LLM_PROVIDER == "ollama":
        # Requires langchain-community installed
        try:
            from langchain_community.chat_models import ChatOllama
        except ImportError:
            raise ImportError(
                "LLM_PROVIDER='ollama' requires `langchain-community` for the RAGAS judge. "
                "Please run: pip install langchain-community"
            )
        # Note: Local LLM evaluation often performs worse as a RAGAS judge unless using a very large model (e.g. llama3 70B).
        # We explicitly support it here for full consistency with the zero-cost spec.
        llm = ChatOllama(model=settings.LLM_MODEL, base_url="http://localhost:11434")
        return LangchainLLMWrapper(llm)
        
    else:
        raise ValueError(f"Unsupported LLM_PROVIDER for RAGAS evaluation: {settings.LLM_PROVIDER}")
