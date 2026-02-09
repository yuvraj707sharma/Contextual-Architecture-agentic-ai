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
def create_llm_client(
    provider: str = "deepseek",
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> BaseLLMClient:
    """
    Factory function to create an LLM client.
    
    Args:
        provider: One of 'deepseek', 'ollama', 'openai', 'anthropic', 'mock'
        model: Optional model override
        api_key: Optional API key override
    
    Returns:
        BaseLLMClient instance
    """
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
    elif provider == "mock":
        return MockLLMClient()
    else:
        raise ValueError(f"Unknown provider: {provider}")
