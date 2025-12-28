#!/usr/bin/env python3
"""
LLM Analyzer Factory

Factory module to create the appropriate LLM analyzer based on configuration.
Supports: Ollama (local), Gemini (cloud), or None (disabled).

Author: Forex Bot Team
Created: 2025-12-27
"""

import logging
from typing import Optional, Union

logger = logging.getLogger(__name__)


def create_llm_analyzer(
    provider: str = "none", rate_limit_seconds: int = 3600, **kwargs
) -> Optional[Union["GeminiMarketAnalyzer", "OllamaMarketAnalyzer"]]:
    """
    Factory function to create an LLM analyzer based on provider.

    Args:
        provider: "none", "ollama", or "gemini"
        rate_limit_seconds: Rate limit between calls per symbol
        **kwargs: Additional arguments passed to the analyzer

    Returns:
        Configured analyzer or None if disabled
    """
    provider = provider.lower().strip()

    if provider == "none" or not provider:
        logger.info("LLM provider set to 'none' - AI analysis disabled")
        return None

    elif provider == "ollama":
        try:
            from utils.ollama_analyzer import OllamaMarketAnalyzer
            from config import (
                OLLAMA_MODEL,
                OLLAMA_HOST,
                OLLAMA_TIMEOUT,
                OLLAMA_TEMPERATURE,
            )

            analyzer = OllamaMarketAnalyzer(
                model=kwargs.get("model", OLLAMA_MODEL),
                host=kwargs.get("host", OLLAMA_HOST),
                timeout=kwargs.get("timeout", OLLAMA_TIMEOUT),
                temperature=kwargs.get("temperature", OLLAMA_TEMPERATURE),
                rate_limit_seconds=rate_limit_seconds,
            )

            if analyzer.enabled:
                logger.info(f"Created Ollama analyzer with model {analyzer.model}")
                return analyzer
            else:
                logger.warning("Ollama server not available, falling back to disabled")
                return None

        except ImportError as e:
            logger.error(f"Failed to import Ollama analyzer: {e}")
            return None

    elif provider == "gemini":
        try:
            from utils.gemini_analyzer import GeminiMarketAnalyzer
            from config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_TEMPERATURE

            analyzer = GeminiMarketAnalyzer(
                api_key=kwargs.get("api_key", GEMINI_API_KEY),
                model_name=kwargs.get("model", GEMINI_MODEL),
                temperature=kwargs.get("temperature", GEMINI_TEMPERATURE),
                rate_limit_seconds=rate_limit_seconds,
            )

            if analyzer.enabled:
                logger.info(f"Created Gemini analyzer with model {analyzer.model_name}")
                return analyzer
            else:
                logger.warning(
                    "Gemini not available (missing API key?), falling back to disabled"
                )
                return None

        except ImportError as e:
            logger.error(f"Failed to import Gemini analyzer: {e}")
            return None

    else:
        logger.error(f"Unknown LLM provider: {provider}")
        return None


def get_analyzer_info(analyzer) -> dict:
    """Get information about the configured analyzer."""
    if analyzer is None:
        return {
            "enabled": False,
            "provider": "none",
            "model": None,
        }

    # Detect provider type
    provider = getattr(analyzer, "provider", None)
    if provider is None:
        # Infer from class name
        class_name = analyzer.__class__.__name__
        if "Ollama" in class_name:
            provider = "ollama"
        elif "Gemini" in class_name:
            provider = "gemini"
        else:
            provider = "unknown"

    return {
        "enabled": getattr(analyzer, "enabled", False),
        "provider": provider,
        "model": getattr(analyzer, "model", None)
        or getattr(analyzer, "model_name", None),
        "rate_limit_seconds": getattr(analyzer, "rate_limit_seconds", 0),
    }
