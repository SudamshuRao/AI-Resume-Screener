"""Groq-backed client with the same interface as the former GeminiClient.

All agent nodes call GeminiClient — this drop-in replacement routes to
Groq (free tier, no billing required) without touching any node code.
"""
import logging
import time

from groq import Groq, APIStatusError, APITimeoutError, APIConnectionError

from agents.config import settings

_logger = logging.getLogger(__name__)

# Errors that are transient and worth retrying
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_BACKOFF_BASE = 2.0  # seconds


class _Response:
    def __init__(self, content: str):
        self.content = content


class GeminiClient:
    """Drop-in replacement that routes LLM calls to Groq instead of Gemini."""

    def __init__(
        self,
        model: str = "",
        temperature: float = 0.0,
        api_key: str = "",
        google_api_key: str = "",     # kept for backward-compat, ignored
        json_mode: bool = False,
        max_output_tokens: int = 8192,
    ):
        resolved_key = api_key or settings.groq_api_key
        if not resolved_key:
            raise ValueError("GROQ_API_KEY is not configured.")
        self._client = Groq(api_key=resolved_key)
        self._model = settings.groq_model
        self._temperature = min(temperature, 1.0)   # Groq max is 1.0 for some models
        self._json_mode = json_mode
        self._max_output_tokens = max_output_tokens

        self.input_tokens: int = 0
        self.output_tokens: int = 0

    def invoke(self, messages) -> _Response:
        prompt = messages[0].content if hasattr(messages[0], "content") else str(messages[0])

        # Groq requires the word "json" in the prompt when using json_object response_format
        if self._json_mode and "json" not in prompt.lower():
            prompt = prompt + "\n\nRespond with valid JSON only."

        kwargs: dict = {
            "model": self._model,
            "temperature": self._temperature,
            "max_tokens": self._max_output_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if self._json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = self._client.chat.completions.create(**kwargs)
                usage = resp.usage
                if usage:
                    self.input_tokens += usage.prompt_tokens or 0
                    self.output_tokens += usage.completion_tokens or 0
                return _Response(resp.choices[0].message.content)
            except APIStatusError as exc:
                if exc.status_code not in _RETRYABLE_STATUS_CODES:
                    raise
                last_exc = exc
                _logger.warning(
                    "Groq API HTTP %d on attempt %d/%d, retrying in %.1fs...",
                    exc.status_code, attempt, _MAX_RETRIES, _BACKOFF_BASE ** attempt,
                )
            except (APITimeoutError, APIConnectionError) as exc:
                last_exc = exc
                _logger.warning(
                    "Groq transient error on attempt %d/%d: %s, retrying in %.1fs...",
                    attempt, _MAX_RETRIES, exc, _BACKOFF_BASE ** attempt,
                )

            if attempt < _MAX_RETRIES:
                time.sleep(_BACKOFF_BASE ** attempt)

        raise RuntimeError(f"Groq API failed after {_MAX_RETRIES} attempts") from last_exc