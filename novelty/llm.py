"""LLM backend - unified interface for Ollama and OpenAI-compatible APIs."""

import json
import time
import urllib.request
from typing import Dict, List, Optional


class LLMClient:
    """Unified LLM client."""

    def __init__(self, provider: str = "ollama", model: str = "",
                 base_url: str = "", api_key: str = ""):
        self.provider = provider
        self.model = model

        if provider == "ollama":
            self.base_url = (base_url or "http://localhost:11434").rstrip("/")
        elif provider in ("openai", "mimo"):
            self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        else:
            self.base_url = base_url.rstrip("/") if base_url else ""

        self.api_key = api_key
        self.history = []  # conversation history

    def chat(self, messages: List[Dict], temperature: float = 0.8,
             max_tokens: int = 2048) -> str:
        """Send messages and get response text."""
        if self.provider == "ollama":
            return self._chat_ollama(messages, temperature, max_tokens)
        else:
            return self._chat_openai(messages, temperature, max_tokens)

    def _chat_ollama(self, messages, temperature, max_tokens) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            resp = urllib.request.urlopen(req, timeout=300)
            result = json.loads(resp.read().decode())
            return result.get("message", {}).get("content", "")
        except Exception as e:
            return f"[LLM Error: {e}]"

    def _chat_openai(self, messages, temperature, max_tokens) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            headers=headers,
        )
        try:
            resp = urllib.request.urlopen(req, timeout=300)
            result = json.loads(resp.read().decode())
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            return f"[LLM Error: {e}]"

    def to_dict(self) -> Dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "api_key": self.api_key,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "LLMClient":
        return cls(
            provider=data.get("provider", "ollama"),
            model=data.get("model", ""),
            base_url=data.get("base_url", ""),
            api_key=data.get("api_key", ""),
        )
