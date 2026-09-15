"""Provider-agnostic LLM wrapper for Demand Radar's two LLM steps.

Bring your own key — the tool auto-detects the provider from whichever key is set:

    GEMINI_API_KEY / GOOGLE_API_KEY  -> Google Gemini   (default model gemini-3.6-flash)
    OPENAI_API_KEY                   -> OpenAI           (default model gpt-4o-mini)
    ANTHROPIC_API_KEY                -> Anthropic Claude (default model claude-haiku-4-5)

Set `provider:` in the config to force one, or `--provider`. With no key it degrades to a
transparent keyword heuristic, so the tool always runs. The whole pipeline talks to the model
only through `complete_text` / `complete_json`, so the provider lives entirely in this file.

The OpenAI and Anthropic paths follow each SDK's documented shape; the Gemini path is the one
exercised in this repo's CI. All three degrade gracefully on error (per-item heuristic fallback).
"""

from __future__ import annotations

import json
import os
import re
import threading
from typing import Any, Optional

DEFAULT_MODELS = {
    "gemini": "gemini-3.6-flash",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5",
}

# Model-name prefixes used to tell whether a configured model matches the provider,
# so a Gemini model id in a config doesn't get sent to OpenAI/Claude verbatim.
_MODEL_PREFIXES = {
    "gemini": ("gemini",),
    "openai": ("gpt", "o1", "o3", "o4", "chatgpt"),
    "anthropic": ("claude",),
}

_SDK = {"gemini": "google", "openai": "openai", "anthropic": "anthropic"}


class LLM:
    """Wraps Gemini / OpenAI / Anthropic behind one interface, with an offline fallback."""

    def __init__(
        self,
        model: str = "gemini-3.6-flash",
        provider: str = "auto",
        prefer_offline: bool = False,
        force_live: bool = False,
    ):
        self.requested_model = model
        self.provider: Optional[str] = None
        self.model = model
        self._client = None
        self._client_lock = threading.Lock()
        self._last_error: Optional[str] = None
        self.available = self._detect(provider, prefer_offline, force_live)

    # -- provider / model resolution ---------------------------------------
    @staticmethod
    def _pick_provider(explicit: str) -> Optional[str]:
        if explicit and explicit != "auto":
            return explicit
        if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
            return "gemini"
        if os.environ.get("OPENAI_API_KEY"):
            return "openai"
        if os.environ.get("ANTHROPIC_API_KEY"):
            return "anthropic"
        return None

    def _resolve_model(self) -> str:
        m, prov = self.requested_model, self.provider
        if m and any(m.startswith(p) for p in _MODEL_PREFIXES.get(prov, ())):
            return m  # the configured model already belongs to this provider
        return DEFAULT_MODELS.get(prov, m)  # otherwise use the provider's default

    def _sdk_ok(self, provider: str) -> bool:
        try:
            __import__(_SDK[provider])
            return True
        except ImportError:
            self._last_error = f"{provider} SDK not installed (pip install {_SDK[provider]})"
            return False

    def _detect(self, provider: str, prefer_offline: bool, force_live: bool) -> bool:
        if prefer_offline:
            return False
        self.provider = self._pick_provider(provider)
        if force_live:
            self.provider = self.provider or "gemini"
            self.model = self._resolve_model()
            return True
        if self.provider is None:
            self._last_error = ("no LLM credentials — set GEMINI_API_KEY, OPENAI_API_KEY, "
                                "or ANTHROPIC_API_KEY")
            return False
        if not self._sdk_ok(self.provider):
            return False
        self.model = self._resolve_model()
        return True

    # -- client (thread-safe, create-once) ---------------------------------
    @property
    def client(self):
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    self._client = self._build_client()
        return self._client

    def _build_client(self):
        if self.provider == "gemini":
            from google import genai
            return genai.Client()          # reads GEMINI_API_KEY / GOOGLE_API_KEY
        if self.provider == "openai":
            from openai import OpenAI
            return OpenAI()                # reads OPENAI_API_KEY
        if self.provider == "anthropic":
            import anthropic
            return anthropic.Anthropic()   # reads ANTHROPIC_API_KEY
        raise RuntimeError(f"unknown provider: {self.provider}")

    def warmup(self) -> None:
        """Create the client eagerly (call in the main thread before a pool)."""
        if self.available:
            try:
                _ = self.client
            except Exception as e:
                self._last_error = f"{type(e).__name__}: {e}"

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    # -- generation dispatch -----------------------------------------------
    def _generate(self, system, user, max_tokens, temperature, json_mode) -> Optional[str]:
        try:
            if self.provider == "gemini":
                return self._gen_gemini(system, user, max_tokens, temperature, json_mode)
            if self.provider == "openai":
                return self._gen_openai(system, user, max_tokens, json_mode)
            if self.provider == "anthropic":
                return self._gen_anthropic(system, user, max_tokens)
        except Exception as e:  # never let one bad call kill the pipeline
            self._last_error = f"{type(e).__name__}: {e}"
            return None
        return None

    def _gen_gemini(self, system, user, max_tokens, temperature, json_mode, retries=2):
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
                    model=self.model, contents=user, config=config)
            except Exception as e:
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

    def _gen_openai(self, system, user, max_tokens, json_mode):
        kwargs = dict(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
        )
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = self.client.chat.completions.create(**kwargs)
        text = resp.choices[0].message.content if resp.choices else None
        return text.strip() if text else None

    def _gen_anthropic(self, system, user, max_tokens):
        # No temperature (removed on current Claude models); JSON via system instruction.
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        return text.strip() or None

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
        return _extract_json(raw) if raw is not None else None


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
