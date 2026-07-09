# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
eval/ragas_providers.py
-----------------------
Zero-cost LLM providers for RAGAS evaluation.
This ensures we do NOT hit OpenAI or any paid APIs during tests.
"""
from __future__ import annotations

from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from langchain_huggingface import HuggingFaceEmbeddings

from app.config import settings

def get_judge_llm() -> LangchainLLMWrapper:
    """
    Returns a Ragas LangchainLLMWrapper pointing to Groq or Ollama.
    Reads configuration directly from settings.
    """
    provider = settings.LLM_PROVIDER
    
    if provider == "groq":
        import os
        api_key = os.environ.get("GROQ_API_KEY")
        if api_key is None:
            api_key = settings.GROQ_API_KEY
            
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY is not set in configuration. "
                "Cannot run RAGAS zero-cost evaluation via Groq."
            )
            
        from langchain_groq import ChatGroq
        judge_model = settings.EVAL_JUDGE_MODEL or settings.LLM_MODEL
        llm = ChatGroq(
            model=judge_model,
            groq_api_key=settings.GROQ_API_KEY,
            temperature=0,
            max_tokens=512,
        )
        return LangchainLLMWrapper(llm)
        
    elif provider == "ollama":
        # Ollama local hosting judge branch
        try:
            from langchain_community.chat_models import ChatOllama
        except ImportError:
            from langchain_ollama import ChatOllama
        llm = ChatOllama(
            model=settings.LLM_MODEL,
            base_url=settings.OLLAMA_BASE_URL,
            temperature=0
        )
        return LangchainLLMWrapper(llm)
        
    else:
        raise ValueError(f"Unsupported LLM_PROVIDER for RAGAS eval: {provider}")

def get_judge_embeddings() -> LangchainEmbeddingsWrapper:
    """
    Returns a Ragas LangchainEmbeddingsWrapper pointing to our local HuggingFace embedding model.
    Reads EMBEDDING_MODEL directly from settings to ensure index model consistency.
    """
    if not settings.EMBEDDING_MODEL:
        raise ValueError("EMBEDDING_MODEL is not set in configuration. Cannot configure Ragas embeddings.")
    embeddings = HuggingFaceEmbeddings(model_name=settings.EMBEDDING_MODEL)
    return LangchainEmbeddingsWrapper(embeddings)
