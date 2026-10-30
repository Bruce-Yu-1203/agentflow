"""Model calls with a small testable response contract."""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ModelReply:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    assistant_content: list[dict[str, Any]] = field(default_factory=list)
    truncated: bool = False


class ModelClient(Protocol):
    async def complete(
        self,
        *,
        stage: str,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        timeout: float = 15.0,
    ) -> ModelReply: ...


class AnthropicModelClient:
    def __init__(self, api_key: str, base_url: str = ""):
        if not api_key:
            raise ValueError("A model API key is required for live model calls")
        from anthropic import AsyncAnthropic

        kwargs: dict[str, Any] = {"api_key": api_key, "max_retries": 0}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = AsyncAnthropic(**kwargs)

    async def complete(
        self,
        *,
        stage: str,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        timeout: float = 15.0,
    ) -> ModelReply:
        kwargs: dict[str, Any] = {
            "model": model,
            "system": system,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
        response = await asyncio.wait_for(self._client.messages.create(**kwargs), timeout=timeout)
        content: list[dict[str, Any]] = []
        calls: list[ToolCall] = []
        text: list[str] = []
        for block in response.content or []:
            kind = getattr(block, "type", None)
            if kind == "text":
                value = str(getattr(block, "text", ""))
                content.append({"type": "text", "text": value})
                text.append(value)
            elif kind == "tool_use":
                arguments = getattr(block, "input", {})
                if not isinstance(arguments, dict):
                    arguments = {}
                call = ToolCall(str(block.id), str(block.name), arguments)
                calls.append(call)
                content.append({"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments})
        return ModelReply("\n".join(text).strip(), calls, content, response.stop_reason == "max_tokens")

    async def close(self) -> None:
        await self._client.close()
