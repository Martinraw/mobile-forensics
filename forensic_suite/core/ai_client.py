"""DeepSeek chat API client (REST, SSE streaming, offline fallback)."""
from __future__ import annotations

import json
from typing import Iterator

import requests

from .config import Config

MODEL_OPTIONS: dict[str, str] = {
    "DeepSeek V4-Flash (free)": "deepseek-chat",
    "DeepSeek V4-Pro": "deepseek-reasoner",
}

OFFLINE_RESPONSE = (
    "**AI assistant is offline — no API key configured.**\n\n"
    "Add your DeepSeek API key in *Settings → AI* or in the AI Assistant tab. "
    "Until then I can give generic forensic guidance.\n\n"
    "Suggestion for this case: 1) acquire logical + file-system data, "
    "2) hash every artifact with SHA-256 and keep the chain of custody, "
    "3) parse WhatsApp/SMS into the case DB, 4) before analysing anything, "
    "verify the acquisition manifests are intact."
)


class AIClient:
    """Wrapper around the DeepSeek /chat/completions endpoint."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()
        self.base_url = self.config.get("ai", "base_url", "https://api.deepseek.com").rstrip("/")

    @property
    def api_key(self) -> str:
        return self.config.get("ai", "api_key", "")

    @property
    def model(self) -> str:
        return self.config.get("ai", "model", "deepseek-chat")

    @property
    def temperature(self) -> float:
        return float(self.config.get("ai", "temperature", 0.4))

    @property
    def ready(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"}

    def _payload(self, messages, model: str | None, temperature: float | None, stream: bool) -> dict:
        return {
            "model": model or self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "stream": stream,
        }

    def chat(self, messages: list[dict], model: str | None = None,
             temperature: float | None = None) -> str:
        """Full (non-streaming) completion."""
        if not self.ready:
            return OFFLINE_RESPONSE
        r = requests.post(f"{self.base_url}/chat/completions",
                          headers=self._headers(),
                          json=self._payload(messages, model, temperature, stream=False),
                          timeout=90)
        r.raise_for_status()
        data = r.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            return "Error: unexpected API response shape."

    def stream_chat(self, messages: list[dict], model: str | None = None,
                    temperature: float | None = None) -> Iterator[str]:
        """Yield response chunks from the SSE stream."""
        if not self.ready:
            yield OFFLINE_RESPONSE
            return
        with requests.post(f"{self.base_url}/chat/completions",
                           headers=self._headers(),
                           json=self._payload(messages, model, temperature, stream=True),
                           stream=True, timeout=180) as r:
            r.raise_for_status()
            for line in r.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    delta = json.loads(payload)["choices"][0]["delta"].get("content", "")
                except (KeyError, IndexError, json.JSONDecodeError):
                    continue
                if delta:
                    yield delta