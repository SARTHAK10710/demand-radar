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
import threading
from typing import Any, Optional


class LLM:
    """Wraps the Gemini client with JSON parsing and a graceful offline mode."""

    def __init__(
        self,
        model: str = "gemini-3.6-flash",
        prefer_offline: bool = False,
        force_live: bool = False,
    ):
        self.model = model
        self._client = None
        self._client_lock = threading.Lock()
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
        # Thread-safe, create-once. Without the lock, concurrent classify workers
        # can each build a genai.Client(); an orphaned one gets GC'd mid-request and
        # raises "client has been closed". One canonical client, held on the instance,
        # keeps a stable strong reference for the life of the run.
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    from google import genai

                    # Reads GEMINI_API_KEY (or GOOGLE_API_KEY) from the environment.
                    self._client = genai.Client()
        return self._client

    def warmup(self) -> None:
        """Create the client eagerly (call in the main thread before a pool)."""
        if self.available:
            try:
                _ = self.client
            except Exception as e:  # offline/no-key stays graceful
                self._last_error = f"{type(e).__name__}: {e}"

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
        retries: int = 2,
    ) -> Optional[str]:
        """One generation, with 429 backoff. Returns the text, or None on failure."""
        import time

        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            temperature=temperature,
            response_mime_type="application/json" if json_mode else "text/plain",
        )
        for attempt in range(retries + 1):
            try:
                resp = self.client.models.generate_content(
                    model=self.model, contents=user, config=config
                )
            except Exception as e:  # never let one bad call kill the pipeline
                self._last_error = f"{type(e).__name__}: {e}"
                if _is_rate_limit(e) and attempt < retries:
                    time.sleep(_retry_delay(str(e), attempt))
                    continue
                return None

            text = getattr(resp, "text", None)
            if not text:
                self._last_error = "empty response (possibly safety-blocked or truncated)"
                return None
            return text.strip()
        return None

    # -- public helpers -----------------------------------------------------
    def complete_text(
        self, system: str, user: str, max_tokens: int = 1024,
        temperature: float = 0.7, effort: str | None = None,
    ) -> Optional[str]:
        return self._generate(system, user, max_tokens, temperature, json_mode=False)

    def complete_json(
        self, system: str, user: str, max_tokens: int = 1024,
        temperature: float = 0.0, effort: str | None = None,
    ) -> Optional[dict[str, Any]]:
        raw = self._generate(system, user, max_tokens, temperature, json_mode=True)
        if raw is None:
            return None
        return _extract_json(raw)


def _is_rate_limit(e: Exception) -> bool:
    s = str(e)
    return "429" in s or "RESOURCE_EXHAUSTED" in s


def _retry_delay(message: str, attempt: int) -> float:
    """Honour the server's retry hint when present, else exponential backoff (<=40s)."""
    m = re.search(r"retry in (\d+(?:\.\d+)?)s", message) or re.search(
        r"'retryDelay':\s*'(\d+(?:\.\d+)?)s'", message
    )
    if m:
        return min(float(m.group(1)) + 1.0, 40.0)
    return min(5.0 * (2 ** attempt), 40.0)


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
