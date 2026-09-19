"""OpenAI-compatible LLM seam. Points at ollama locally, or any hosted endpoint via env."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Sequence

import openai

from manus.config import Config


class LLMError(RuntimeError):
    """An LLM call failed in a way the user can act on."""


@dataclass
class ToolCall:
    """One requested tool invocation. `arguments` is a JSON object string."""

    name: str
    arguments: str
    id: str = ""


@dataclass
class LLMResponse:
    content: str
    tool_call: Optional[ToolCall]
    finish_reason: str


class LLMClient:
    """Thin wrapper over the openai SDK adding local-model robustness.

    - sends `reasoning_effort` only when configured, and retries once without it
      when a server rejects the field (OpenAI-compat servers disagree on it)
    - returns the first tool call only (the agent loop executes one per iteration)
    - converts transport/auth failures into a typed, actionable LLMError
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        self._client: Optional[openai.OpenAI] = None

    def _ensure_client(self) -> openai.OpenAI:
        if self._client is None:
            self._client = openai.OpenAI(
                base_url=self._config.base_url, api_key=self._config.api_key
            )
        return self._client

    def chat(self, messages: List[dict], tool_schemas: Sequence[dict]) -> LLMResponse:
        client = self._ensure_client()
        kwargs: dict[str, Any] = {
            "model": self._config.model,
            "messages": messages,
            "max_tokens": self._config.step_max_tokens,
        }
        if tool_schemas:
            kwargs["tools"] = [{"type": "function", "function": schema} for schema in tool_schemas]
        if self._config.reasoning_effort:
            kwargs["reasoning_effort"] = self._config.reasoning_effort

        try:
            response = client.chat.completions.create(**kwargs)
        except openai.BadRequestError as exc:
            if "reasoning_effort" in kwargs and "reasoning_effort" in str(exc):
                kwargs.pop("reasoning_effort")
                try:
                    response = client.chat.completions.create(**kwargs)
                except openai.APIError as retry_exc:
                    raise LLMError(
                        "LLM rejected the request even without reasoning_effort: " f"{retry_exc}"
                    ) from retry_exc
            else:
                raise LLMError(f"LLM rejected the request: {exc}") from exc
        except openai.APIConnectionError as exc:
            raise LLMError(
                f"Cannot reach the LLM endpoint at {self._config.base_url} "
                f"(model {self._config.model}). Is ollama running? (`ollama serve`)"
            ) from exc
        except openai.AuthenticationError as exc:
            raise LLMError(
                f"LLM endpoint at {self._config.base_url} rejected the API key. "
                "Set MANUS_API_KEY if your endpoint requires one."
            ) from exc

        if not response.choices:
            raise LLMError("LLM returned an empty response (no choices).")
        choice = response.choices[0]
        message = choice.message
        tool_call: Optional[ToolCall] = None
        if getattr(message, "tool_calls", None):
            first = message.tool_calls[0]
            tool_call = ToolCall(
                name=first.function.name,
                arguments=first.function.arguments or "{}",
                id=first.id or "",
            )
        return LLMResponse(
            content=message.content or "",
            tool_call=tool_call,
            finish_reason=choice.finish_reason or "",
        )
