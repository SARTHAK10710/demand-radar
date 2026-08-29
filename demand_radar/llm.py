"""Thin wrapper around Google Gemini for Demand Radar's two LLM steps.

The whole pipeline talks to the model through just this class, so the provider
lives in one place. Two design goals:
  1. Keep provider details (SDK, JSON mode, model id) isolated here.
  2. Degrade gracefully. With no GEMINI_API_KEY the tool still runs end to end
     using heuristic fallbacks, so it is always demoable; with a key it uses
     Gemini for the real classification and outreach.

Uses the unified `google-genai` SDK (`from google import genai`). Get a free key
at https://aistudio.google.com/apikey and set GEMINI_API_KEY.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Optional


class LLM:
    """Wraps the Gemini client with JSON parsing and a graceful offline mode."""

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        prefer_offline: bool = False,
        force_live: bool = False,
    ):
        self.model = model
        self._client = None
        self._last_error: Optional[str] = None
        self.available = self._detect(prefer_offline, force_live)

    # -- availability -------------------------------------------------------
    @staticmethod
    def _has_credentials() -> bool:
        return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))

    def _detect(self, prefer_offline: bool, force_live: bool) -> bool:
        if prefer_offline:
            return False
        if force_live:
            return True
        try:
            from google import genai  # noqa: F401
        except ImportError:
            self._last_error = "google-genai SDK not installed (`pip install google-genai`)"
            return False
        return self._has_credentials()

    @property
    def client(self):
        if self._client is None:
            from google import genai

            # Reads GEMINI_API_KEY (or GOOGLE_API_KEY) from the environment.
            self._client = genai.Client()
        return self._client

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    # -- raw generation -----------------------------------------------------
    def _generate(
        self,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
        json_mode: bool,
    ) -> Optional[str]:
        """One generation. Returns the text, or None on any failure."""
        try:
            from google.genai import types

            config = types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=max_tokens,
                temperature=temperature,
                response_mime_type="application/json" if json_mode else "text/plain",
            )
            resp = self.client.models.generate_content(
                model=self.model, contents=user, config=config
            )
        except Exception as e:  # never let one bad call kill the pipeline
            self._last_error = f"{type(e).__name__}: {e}"
            return None

        text = getattr(resp, "text", None)
        if not text:
            self._last_error = "empty response (possibly safety-blocked or truncated)"
            return None
        return text.strip()

    # -- public helpers -----------------------------------------------------
    def complete_text(
        self, system: str, user: str, max_tokens: int = 400,
        temperature: float = 0.7, effort: str | None = None,
    ) -> Optional[str]:
        return self._generate(system, user, max_tokens, temperature, json_mode=False)

    def complete_json(
        self, system: str, user: str, max_tokens: int = 400,
        temperature: float = 0.0, effort: str | None = None,
    ) -> Optional[dict[str, Any]]:
        raw = self._generate(system, user, max_tokens, temperature, json_mode=True)
        if raw is None:
            return None
        return _extract_json(raw)


def _extract_json(text: str) -> Optional[dict[str, Any]]:
    """Tolerant JSON extraction — models sometimes wrap JSON in prose or fences."""
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None
