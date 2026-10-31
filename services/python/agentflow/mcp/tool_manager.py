"""Tool registration, schema validation, caching, timeouts, and circuit breaking."""

import asyncio
from dataclasses import dataclass
import inspect
import json
import time
from typing import Any, Callable

from jsonschema import Draft202012Validator


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    properties: dict[str, Any]
    required: tuple[str, ...]
    roles: frozenset[str]
    handler: Callable[..., dict[str, Any]]
    retry_safe: bool = True
    timeout: float = 5.0
    cache_ttl: float = 30.0
    input_schema: dict[str, Any] | None = None
    pass_role: bool = False

    @property
    def schema(self) -> dict[str, Any]:
        return self.input_schema or {"type": "object", "properties": self.properties, "required": list(self.required), "additionalProperties": False}

    def model_definition(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "input_schema": self.schema}


class ToolRegistry:
    def __init__(self, specs: list[ToolSpec] | None = None):
        from agentflow.agents.tools import TOOL_SPECS

        self._specs = {spec.name: spec for spec in (specs or TOOL_SPECS)}
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._failures: dict[str, int] = {}
        self._retry_at: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def definitions(self, role: str) -> list[dict[str, Any]]:
        return [spec.model_definition() for spec in self._specs.values() if role in spec.roles]

    def register_knowledge(self, knowledge: Any) -> None:
        from agentflow.agents.tools import STRING

        async def search_knowledge_base(query: str, top_k: int = 5) -> dict[str, Any]:
            return {"results": await knowledge.search(query, top_k)}
        self._specs["search_knowledge_base"] = ToolSpec(
            "search_knowledge_base", "Retrieve approved knowledge passages with provenance.",
            {"query": STRING, "top_k": {"type": "integer", "minimum": 1, "maximum": 20}}, ("query",),
            frozenset({"general", "technical", "billing"}), search_knowledge_base,
        )

    async def refresh_mcp(self, manager: Any) -> None:
        discovered = await manager.discover()
        self._specs = {name: spec for name, spec in self._specs.items() if not name.startswith("mcp__")}
        for tool in discovered:
            async def external(role: str, *_, _alias=tool["remote_alias"], **arguments: Any) -> dict[str, Any]:
                return await manager.call(role, _alias, arguments)
            self._specs[tool["alias"]] = ToolSpec(tool["alias"], tool["description"], {}, (), frozenset(tool["roles"]), external, True, 10.0, 0.0, tool["schema"], True)

    def invalidate(self, name: str | None = None) -> None:
        self._cache = {key: value for key, value in self._cache.items() if name is not None and not key.startswith(name + ":")}

    def retry_safe(self, name: str) -> bool:
        return self._specs[name].retry_safe

    async def execute(self, role: str, name: str, arguments: dict[str, Any], *, scope: str = "") -> dict[str, Any]:
        spec = self._specs.get(name)
        if spec is None or role not in spec.roles:
            raise PermissionError(f"Tool {name} is not permitted for {role}")
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be an object")
        errors = list(Draft202012Validator(spec.schema).iter_errors(arguments))
        if errors:
            raise ValueError(f"Invalid tool arguments: {errors[0].message}")
        cache_key = name + ":" + json.dumps([scope, arguments], sort_keys=True)
        lock = self._locks.setdefault(name, asyncio.Lock())
        async with lock:
            cached = self._cache.get(cache_key)
            if cached and time.monotonic() < cached[0]:
                return cached[1]
            if time.monotonic() < self._retry_at.get(name, 0):
                raise RuntimeError("Tool circuit is open")
            try:
                if inspect.iscoroutinefunction(spec.handler):
                    output = await asyncio.wait_for(spec.handler(role, **arguments) if spec.pass_role else spec.handler(**arguments), timeout=spec.timeout)
                else:
                    output = await asyncio.wait_for(asyncio.to_thread(spec.handler, role, **arguments) if spec.pass_role else asyncio.to_thread(spec.handler, **arguments), timeout=spec.timeout)
                self._failures[name] = 0
                self._retry_at.pop(name, None)
                if spec.cache_ttl > 0:
                    self._cache[cache_key] = (time.monotonic() + spec.cache_ttl, output)
                return output
            except Exception:
                failures = self._failures.get(name, 0) + 1
                self._failures[name] = failures
                if failures >= 5:
                    self._retry_at[name] = time.monotonic() + 60
                raise
