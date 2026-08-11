from __future__ import annotations

import json
import logging
from typing import Any

import requests

from src.config import Settings

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def chat_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        payload = {
            "model": self.settings.openai_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "response_format": {"type": "json_object"},
        }
        response = requests.post(
            f"{self.settings.openai_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": self.settings.base_url or "https://github.com",
                "X-Title": "Personal News Digest",
            },
            json=payload,
            timeout=self.settings.openai_timeout,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            logger.error("LLM returned non-JSON content: %s", content[:500])
            raise
