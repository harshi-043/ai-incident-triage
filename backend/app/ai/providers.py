"""
Optional AI providers. All calls go through httpx with a timeout. With `AI_PROVIDER=none` (the default) nothing is called.

The API key comes only from the environment (Settings.ai_api_key). It is sent only in the request header, never logged,
never returned by the API and never included in an error message.

HONESTY NOTE: these classes were tested with mocked HTTP responses only. No real provider was called while building this
project (no API key was available), so the request formats follow each provider's public documentation but are not
confirmed against the live services.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Protocol

import httpx

from app.core.config import Settings

logger = logging.getLogger("triage")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
MAX_RESPONSE_CHARS = 20_000


class ProviderError(Exception):
    """A failure that the caller turns into a fallback (never a crash). `code` is stable; `message` is safe to show."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


class Provider(Protocol):
    name: str

    def complete(self, system: str, user: str) -> str: ...


def _post(client: httpx.Client | None, url: str, headers: dict[str, str], body: dict, timeout: float) -> dict:
    """POST JSON and return the decoded JSON body, turning every failure into a ProviderError without secrets in it."""
    try:
        if client is not None:
            response = client.post(url, headers=headers, json=body, timeout=timeout)
        else:
            with httpx.Client(timeout=timeout, follow_redirects=False) as owned:
                response = owned.post(url, headers=headers, json=body)
    except httpx.TimeoutException:
        raise ProviderError("ai_timeout", f"The AI provider did not answer within {timeout:g} seconds.") from None
    except httpx.HTTPError:
        raise ProviderError("ai_unreachable", "The AI provider could not be reached.") from None
    if response.status_code in (401, 403):
        raise ProviderError("ai_auth_failed", "The AI provider rejected the credentials. Check AI_API_KEY.")
    if response.status_code == 429:
        raise ProviderError("ai_rate_limited", "The AI provider is rate limiting requests. Try again later.")
    if response.status_code >= 400:
        raise ProviderError("ai_provider_error", f"The AI provider returned an error (HTTP {response.status_code}).")
    try:
        data = response.json()
    except ValueError:
        raise ProviderError("ai_bad_response", "The AI provider did not return JSON.") from None
    if not isinstance(data, dict):
        raise ProviderError("ai_bad_response", "The AI provider returned an unexpected response.")
    return data


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings, self.client = settings, client
        self.model = settings.ai_model or ""

    def complete(self, system: str, user: str) -> str:
        data = _post(self.client, (self.settings.ai_base_url or ANTHROPIC_URL),
                     {"x-api-key": self.settings.ai_api_key or "", "anthropic-version": "2023-06-01", "content-type": "application/json"},
                     {"model": self.model, "max_tokens": 1500, "system": system, "messages": [{"role": "user", "content": user}]},
                     self.settings.ai_timeout_seconds)
        try:
            blocks = data["content"]
            if not isinstance(blocks, list):
                raise TypeError("content is not a list")
            parts = [b["text"] for b in blocks if isinstance(b, dict) and b.get("type") == "text"]
            return "".join(parts)[:MAX_RESPONSE_CHARS]
        except (KeyError, TypeError, AttributeError):
            raise ProviderError("ai_bad_response", "The AI provider's answer had an unexpected shape.") from None


class OpenAIProvider:
    """Also used for 'openai_compatible' servers (set AI_BASE_URL to the full chat-completions URL)."""

    def __init__(self, settings: Settings, client: httpx.Client | None = None, *, compatible: bool = False) -> None:
        self.settings, self.client, self.compatible = settings, client, compatible
        self.name = "openai_compatible" if compatible else "openai"
        self.model = settings.ai_model or ""

    def complete(self, system: str, user: str) -> str:
        url = self.settings.ai_base_url if self.compatible else (self.settings.ai_base_url or OPENAI_URL)
        body: dict = {"model": self.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if self.compatible:  # parameters that most compatible servers accept; the official API's newer models can reject them
            body.update({"max_tokens": 1500, "temperature": 0.2})
        headers = {"content-type": "application/json"}
        if self.settings.ai_api_key:
            headers["authorization"] = f"Bearer {self.settings.ai_api_key}"
        data = _post(self.client, url or "", headers, body, self.settings.ai_timeout_seconds)
        try:
            return str(data["choices"][0]["message"]["content"] or "")[:MAX_RESPONSE_CHARS]
        except (KeyError, IndexError, TypeError):
            raise ProviderError("ai_bad_response", "The AI provider's answer had an unexpected shape.") from None


def ai_configuration_problem(settings: Settings) -> str | None:
    """Why the AI provider cannot be used right now, or None when it is ready (or deliberately off)."""
    provider = settings.ai_provider
    if provider == "none":
        return None
    if provider not in ("anthropic", "openai", "openai_compatible"):
        return f"Unknown AI_PROVIDER '{provider}'. Use none, anthropic, openai or openai_compatible."
    if not settings.ai_model:
        return "AI_MODEL is not set."
    if provider != "openai_compatible" and not settings.ai_api_key:
        return "AI_API_KEY is not set."
    if provider == "openai_compatible" and not settings.ai_base_url:
        return "AI_BASE_URL is not set."
    return None


def make_provider(settings: Settings, client: httpx.Client | None = None) -> Provider | None:
    """The configured provider, or None when AI is off or not fully configured."""
    if settings.ai_provider == "none" or ai_configuration_problem(settings):
        return None
    if settings.ai_provider == "anthropic":
        return AnthropicProvider(settings, client)
    return OpenAIProvider(settings, client, compatible=settings.ai_provider == "openai_compatible")


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def parse_json_object(text: str) -> dict:
    """Decode a model's reply into a JSON object. Accepts a reply wrapped in a code fence; anything else is an error."""
    cleaned = _FENCE.sub("", (text or "").strip()).strip()
    try:
        value = json.loads(cleaned)
    except ValueError:
        start, end = cleaned.find("{"), cleaned.rfind("}")  # a model may add a sentence around the JSON
        try:
            value = json.loads(cleaned[start:end + 1]) if 0 <= start < end else None
        except ValueError:
            value = None
    if not isinstance(value, dict):
        raise ProviderError("ai_bad_response", "The AI answer was not a valid JSON object.")
    return value
