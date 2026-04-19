"""
llm_provider.py
───────────────
Provider abstraction module for sequential LLM failover.
"""

import logging
from abc import ABC, abstractmethod

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

from app.config import (
    GEMINI_API_KEY_PRIMARY,
    GEMINI_API_KEY_SECONDARY,
    GROQ_API_KEY,
    GEMINI_MODEL,
    GROQ_MODEL,
    LLM_REQUEST_TIMEOUT,
)

logger = logging.getLogger(__name__)


class ProviderQuotaError(Exception):
    pass

class ProviderRateLimitError(Exception):
    pass

class ProviderTimeoutError(Exception):
    pass

class ProviderInternalError(Exception):
    pass


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Generate text from system and human prompt structures."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass


class GeminiProviderBase(LLMProvider):
    def __init__(self, key: str, name: str):
        self._name = name
        if not key:
            raise ValueError(f"Missing API key for {self._name}")

        self._llm = ChatGoogleGenerativeAI(
            model=GEMINI_MODEL,
            google_api_key=key,
            temperature=0.2,
            timeout=LLM_REQUEST_TIMEOUT,
            max_retries=0, # Orchestration handles all retries
        )

    @property
    def name(self) -> str:
        return self._name

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        try:
            resp = await self._llm.ainvoke(messages)
            return resp.content
        except Exception as e:
            err = str(e).lower()
            if "quota" in err or "429" in err:
                raise ProviderQuotaError(err)
            if "rate" in err and "limit" in err:
                raise ProviderRateLimitError(err)
            if "timeout" in err or "timed out" in err:
                raise ProviderTimeoutError(err)
            if "500" in err or "503" in err:
                raise ProviderInternalError(err)
            raise


class GeminiPrimaryProvider(GeminiProviderBase):
    def __init__(self):
        super().__init__(GEMINI_API_KEY_PRIMARY, "Gemini Primary")


class GeminiSecondaryProvider(GeminiProviderBase):
    def __init__(self):
        super().__init__(GEMINI_API_KEY_SECONDARY, "Gemini Secondary")


class GroqProvider(LLMProvider):
    def __init__(self):
        if not GROQ_API_KEY:
            raise ValueError("Missing API key for Groq")

        self._llm = ChatGroq(
            model_name=GROQ_MODEL,
            groq_api_key=GROQ_API_KEY,
            temperature=0.2,
            timeout=LLM_REQUEST_TIMEOUT,
            max_retries=0,
        )

    @property
    def name(self) -> str:
        return "Groq"

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        try:
            resp = await self._llm.ainvoke(messages)
            return resp.content
        except Exception as e:
            err = str(e).lower()
            if "quota" in err or "429" in err:
                raise ProviderQuotaError(err)
            if "rate" in err and "limit" in err:
                raise ProviderRateLimitError(err)
            if "timeout" in err or "timed out" in err:
                raise ProviderTimeoutError(err)
            if "500" in err or "503" in err or "internal" in err:
                raise ProviderInternalError(err)
            raise


async def generate_with_fallback(system_prompt: str, user_prompt: str) -> str:
    """Orchestrates sequential fallovers across multiple LLM providers."""
    providers = []
    
    # Initialize configured providers strictly in sequence
    for ProviderClass in [GeminiPrimaryProvider, GeminiSecondaryProvider, GroqProvider]:
        try:
            providers.append(ProviderClass())
        except ValueError as e:
            logger.warning("Skipping provider due to missing config: %s", e)

    if not providers:
        raise RuntimeError("No LLM providers are configured with valid API keys.")

    for provider in providers:
        logger.info("[LLM] Attempting %s", provider.name)
        try:
            response = await provider.generate(system_prompt, user_prompt)
            if response and str(response).strip():
                logger.info("[LLM] %s success", provider.name)
                return str(response).strip()
        except ProviderQuotaError:
            logger.warning("[LLM] %s failed: quota exceeded", provider.name)
            continue
        except ProviderRateLimitError:
            logger.warning("[LLM] %s failed: rate limit", provider.name)
            continue
        except ProviderTimeoutError:
            logger.warning("[LLM] %s failed: timeout", provider.name)
            continue
        except ProviderInternalError:
            logger.warning("[LLM] %s failed: internal server error", provider.name)
            continue
        except Exception as e:
            logger.warning("[LLM] %s generic failure: %s", provider.name, str(e))
            continue

    raise RuntimeError("All configured LLM providers failed")
