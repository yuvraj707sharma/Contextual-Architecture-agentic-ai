"""
LLM Client - Unified interface for multiple LLM providers.

Supports:
- DeepSeek (cheap, good for code)
- Ollama (free, local)
- OpenAI (GPT-4o)
- Anthropic (Claude)

The system can swap LLMs freely - the agents don't care which one is used.
"""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any, List


@dataclass
class LLMResponse:
    """Response from an LLM call."""
    content: str
    model: str
    usage: Dict[str, int]  # tokens used
    finish_reason: str
    raw_response: Optional[Dict[str, Any]] = None


class BaseLLMClient(ABC):
    """Abstract base class for all LLM clients."""
    
    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Generate a response from the LLM."""
        pass
    
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name of the model being used."""
        pass


class DeepSeekClient(BaseLLMClient):
    """
    DeepSeek API Client.
    
    - Model: deepseek-coder or deepseek-chat
    - Cost: ~$0.14/1M input, $0.28/1M output (VERY cheap)
    - Quality: Nearly GPT-4 level for code
    
    Get API key: https://platform.deepseek.com/
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "deepseek-coder",
        base_url: str = "https://api.deepseek.com/v1"
    ):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY not found")
        
        self.model = model
        self.base_url = base_url
    
    @property
    def model_name(self) -> str:
        return f"deepseek/{self.model}"
    
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        import httpx
        
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
            response.raise_for_status()
            data = response.json()
        
        choice = data["choices"][0]
        return LLMResponse(
            content=choice["message"]["content"],
            model=self.model,
            usage=data.get("usage", {}),
            finish_reason=choice.get("finish_reason", "stop"),
            raw_response=data,
        )


class OllamaClient(BaseLLMClient):
    """
    Ollama Client for local models.
    
    - Cost: FREE (runs on your machine)
    - Models: deepseek-coder-v2, codellama, qwen2.5-coder, etc.
    - Quality: Good for iteration, not production
    
    Install: https://ollama.ai
    Run: ollama run deepseek-coder-v2:16b
    """
    
    def __init__(
        self,
        model: str = "deepseek-coder-v2:16b",
        base_url: str = "http://localhost:11434"
    ):
        self.model = model
        self.base_url = base_url
    
    @property
    def model_name(self) -> str:
        return f"ollama/{self.model}"
    
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        import httpx
        
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "system": system_prompt,
                    "prompt": user_prompt,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    },
                },
            )
            response.raise_for_status()
            data = response.json()
        
        return LLMResponse(
            content=data.get("response", ""),
            model=self.model,
            usage={
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
            },
            finish_reason="stop",
            raw_response=data,
        )


class OpenAIClient(BaseLLMClient):
    """
    OpenAI API Client.
    
    - Models: gpt-4o, gpt-4o-mini
    - Cost: ~$2.50/1M input (4o-mini), ~$5/1M (4o)
    - Quality: Excellent
    
    Get API key: https://platform.openai.com/
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1"
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found")
        
        self.model = model
        self.base_url = base_url
    
    @property
    def model_name(self) -> str:
        return f"openai/{self.model}"
    
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        import httpx
        
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
            response.raise_for_status()
            data = response.json()
        
        choice = data["choices"][0]
        return LLMResponse(
            content=choice["message"]["content"],
            model=self.model,
            usage=data.get("usage", {}),
            finish_reason=choice.get("finish_reason", "stop"),
            raw_response=data,
        )


class AnthropicClient(BaseLLMClient):
    """
    Anthropic API Client (Claude).
    
    - Models: claude-3-5-sonnet, claude-3-opus
    - Cost: ~$3/1M input (Sonnet), ~$15/1M (Opus)
    - Quality: Best for complex reasoning
    
    Get API key: https://console.anthropic.com/
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-3-5-sonnet-20241022"
    ):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not found")
        
        self.model = model
    
    @property
    def model_name(self) -> str:
        return f"anthropic/{self.model}"
    
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        import httpx
        
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "system": system_prompt,
                    "messages": [
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
            response.raise_for_status()
            data = response.json()
        
        content = data.get("content", [{}])[0].get("text", "")
        return LLMResponse(
            content=content,
            model=self.model,
            usage=data.get("usage", {}),
            finish_reason=data.get("stop_reason", "end_turn"),
            raw_response=data,
        )


class MockLLMClient(BaseLLMClient):
    """
    Mock LLM Client for testing.
    
    Returns predefined responses without API calls.
    """
    
    def __init__(self, responses: Optional[List[str]] = None):
        self._responses = responses or ["Mock response"]
        self._call_count = 0
    
    @property
    def model_name(self) -> str:
        return "mock/test"
    
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        response = self._responses[self._call_count % len(self._responses)]
        self._call_count += 1
        
        return LLMResponse(
            content=response,
            model="mock",
            usage={"prompt_tokens": 100, "completion_tokens": 50},
            finish_reason="stop",
        )


# Factory function

def detect_provider_from_key(api_key: str) -> str:
    """
    Detect LLM provider from an API key's prefix.
    
    API key patterns (as of 2026):
      - Anthropic:  sk-ant-*
      - OpenAI:     sk-proj-* or sk-* (longer, typically 50+ chars)
      - DeepSeek:   sk-* (shorter, typically 32-40 chars)
      - Google:     AIza*
      - Mistral:    starts with alphanumeric, no prefix
    
    This is a best-effort heuristic. Users can always override
    with --provider or CA_LLM_PROVIDER.
    """
    if not api_key or not isinstance(api_key, str):
        return "mock"
    
    key = api_key.strip()
    
    # Anthropic — most distinctive prefix
    if key.startswith("sk-ant-"):
        return "anthropic"
    
    # Google Gemini
    if key.startswith("AIza"):
        return "google"
    
    # OpenAI vs DeepSeek — both use "sk-" prefix
    # OpenAI keys typically start with "sk-proj-" (project keys) 
    # or are 51+ characters long
    if key.startswith("sk-proj-"):
        return "openai"
    
    if key.startswith("sk-"):
        # DeepSeek keys are typically shorter (32-50 chars)
        # OpenAI keys are typically longer (51-200+ chars)
        # This is a heuristic — not guaranteed
        if len(key) > 60:
            return "openai"
        else:
            return "deepseek"
    
    # Unknown prefix — return unknown, let caller decide
    return "unknown"


def detect_provider_from_env() -> tuple:
    """
    Auto-detect LLM provider from environment variables.
    
    Checks for known env var names in priority order.
    Returns (provider_name, api_key) tuple.
    
    Priority:
      1. Explicit CA_LLM_PROVIDER (user's choice — always wins)
      2. ANTHROPIC_API_KEY (most distinctive prefix)
      3. OPENAI_API_KEY
      4. DEEPSEEK_API_KEY
      5. GOOGLE_API_KEY / GEMINI_API_KEY
      6. Ollama (check if running locally)
      7. Mock (fallback)
    """
    import os
    
    # If user explicitly set the provider, respect it
    explicit_provider = os.environ.get("CA_LLM_PROVIDER")
    if explicit_provider:
        # Find the matching key
        key_map = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "google": "GOOGLE_API_KEY",
            "ollama": None,
            "mock": None,
        }
        env_var = key_map.get(explicit_provider)
        api_key = os.environ.get(env_var) if env_var else None
        # Also check the generic CA_LLM_API_KEY
        if not api_key:
            api_key = os.environ.get("CA_LLM_API_KEY")
        return (explicit_provider, api_key)
    
    # Auto-detect from env var names (most reliable method)
    env_checks = [
        ("ANTHROPIC_API_KEY", "anthropic"),
        ("OPENAI_API_KEY", "openai"),
        ("DEEPSEEK_API_KEY", "deepseek"),
        ("GOOGLE_API_KEY", "google"),
        ("GEMINI_API_KEY", "google"),
    ]
    
    for env_var, provider in env_checks:
        key = os.environ.get(env_var)
        if key:
            # Double-check with prefix detection
            detected = detect_provider_from_key(key)
            if detected != "unknown" and detected != provider:
                # Key prefix doesn't match env var name — warn user
                import warnings
                warnings.warn(
                    f"API key in {env_var} looks like a {detected} key, "
                    f"not {provider}. Using {detected} instead. "
                    f"Set CA_LLM_PROVIDER={provider} to override.",
                    UserWarning,
                    stacklevel=2,
                )
                return (detected, key)
            return (provider, key)
    
    # Check if a generic API key was provided
    generic_key = os.environ.get("CA_LLM_API_KEY")
    if generic_key:
        detected = detect_provider_from_key(generic_key)
        if detected != "unknown":
            return (detected, generic_key)
        # Can't determine provider from key alone
        return ("unknown", generic_key)
    
    # Check if Ollama is running locally
    try:
        import httpx
        resp = httpx.get("http://localhost:11434/api/version", timeout=2)
        if resp.status_code == 200:
            return ("ollama", None)
    except Exception:
        pass
    
    return ("mock", None)


def create_llm_client(
    provider: str = "auto",
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> BaseLLMClient:
    """
    Factory function to create an LLM client.
    
    Args:
        provider: One of 'deepseek', 'ollama', 'openai', 'anthropic', 
                  'google', 'mock', or 'auto' (auto-detect)
        model: Optional model override
        api_key: Optional API key override
    
    Returns:
        BaseLLMClient instance
    """
    # Auto-detect if provider not specified or is "auto"
    if provider in ("auto", None, ""):
        if api_key:
            # Detect from key prefix
            provider = detect_provider_from_key(api_key)
        else:
            # Detect from environment variables
            provider, api_key = detect_provider_from_env()
    
    if provider == "unknown":
        raise ValueError(
            "Could not auto-detect LLM provider. Please set one of:\n"
            "  - CA_LLM_PROVIDER=deepseek (+ DEEPSEEK_API_KEY)\n"
            "  - CA_LLM_PROVIDER=openai (+ OPENAI_API_KEY)\n"
            "  - CA_LLM_PROVIDER=anthropic (+ ANTHROPIC_API_KEY)\n"
            "  - CA_LLM_PROVIDER=google (+ GOOGLE_API_KEY)\n"
            "  - CA_LLM_PROVIDER=ollama (no key needed)\n"
        )
    
    if provider == "deepseek":
        return DeepSeekClient(
            api_key=api_key,
            model=model or "deepseek-coder",
        )
    elif provider == "ollama":
        return OllamaClient(
            model=model or "deepseek-coder-v2:16b",
        )
    elif provider == "openai":
        return OpenAIClient(
            api_key=api_key,
            model=model or "gpt-4o-mini",
        )
    elif provider == "anthropic":
        return AnthropicClient(
            api_key=api_key,
            model=model or "claude-3-5-sonnet-20241022",
        )
    elif provider == "google":
        # Google/Gemini uses OpenAI-compatible API format
        return OpenAIClient(
            api_key=api_key,
            model=model or "gemini-2.0-flash",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        )
    elif provider == "mock":
        return MockLLMClient()
    else:
        raise ValueError(
            f"Unknown provider: {provider}. "
            f"Supported: deepseek, ollama, openai, anthropic, google, mock"
        )

