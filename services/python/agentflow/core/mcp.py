"""Allowlisted MCP discovery and bounded read-only calls."""

from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import urlsplit

import httpx
from jsonschema import Draft202012Validator
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client


@dataclass(frozen=True)
class MCPServer:
    name: str
    transport: str
    allowed_tools: frozenset[str]
    roles: frozenset[str]
    read_only: bool
    url: str = ""
    command: str = ""
    args: tuple[str, ...] = ()
    env_allowlist: tuple[str, ...] = ()
    headers_env: tuple[tuple[str, str], ...] = ()


class MCPManager:
    def __init__(self, config_path: str):
        path = Path(config_path)
        raw = json.loads(path.read_text()) if path.exists() else []
        if not isinstance(raw, list) or len(raw) > 16:
            raise ValueError("MCP configuration must contain at most 16 servers")
        servers: dict[str, MCPServer] = {}
        for item in raw:
            name = item.get("name", "")
            transport = item.get("transport", "")
            if not name or name in servers or transport not in {"streamable_http", "stdio"}:
                raise ValueError("MCP server names must be unique and transports supported")
            roles = frozenset(item.get("roles", []))
            if not roles or not roles <= {"general", "technical", "billing", "escalation", "admin"}:
                raise ValueError("MCP server roles are invalid")
            url = item.get("url", "")
            headers_env = item.get("headers_env", {})
            if not isinstance(headers_env, dict) or any(not isinstance(name, str) or not isinstance(variable, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", variable) for name, variable in headers_env.items()):
                raise ValueError("MCP headers_env must map header names to environment variables")
            if transport == "streamable_http":
                parsed = urlsplit(url)
                if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                    raise ValueError("MCP HTTP URL must be credential-free HTTP(S)")
            elif not item.get("command"):
                raise ValueError("MCP stdio server requires a command")
            servers[name] = MCPServer(name, transport, frozenset(item.get("allowed_tools", [])), roles, bool(item.get("read_only", True)), url, item.get("command", ""), tuple(item.get("args", [])), tuple(item.get("env_allowlist", [])), tuple(headers_env.items()))
        self.servers = servers
        self._catalog: list[dict[str, Any]] = []
        self._catalog_at = 0.0
        self._states: dict[str, str] = {name: "not_checked" for name in servers}

    async def discover(self) -> list[dict[str, Any]]:
        if time.monotonic() - self._catalog_at < 60:
            return list(self._catalog)
        discovered: list[dict[str, Any]] = []
        for server in self.servers.values():
            if not server.allowed_tools:
                continue
            try:
                async with AsyncExitStack() as stack:
                    if server.transport == "streamable_http":
                        headers = {name: os.environ[variable] for name, variable in server.headers_env if variable in os.environ}
                        client = await stack.enter_async_context(httpx.AsyncClient(timeout=10, follow_redirects=False, headers=headers))
                        read, write = (await stack.enter_async_context(streamable_http_client(server.url, http_client=client)))[:2]
                    else:
                        env = {name: os.environ[name] for name in server.env_allowlist if name in os.environ}
                        read, write = await stack.enter_async_context(stdio_client(StdioServerParameters(command=server.command, args=list(server.args), env=env)))
                    session = await stack.enter_async_context(ClientSession(read, write))
                    await session.initialize()
                    self._states[server.name] = "connected"
                    cursor = None
                    for _ in range(10):
                        page = await session.list_tools(cursor=cursor)
                        for tool in page.tools:
                            if tool.name not in server.allowed_tools:
                                continue
                            hints = tool.annotations
                            if hints is None or hints.readOnlyHint is not True or hints.destructiveHint is True:
                                continue
                            Draft202012Validator.check_schema(tool.inputSchema)
                            raw_alias = "mcp__" + re.sub(r"[^A-Za-z0-9_]", "_", server.name + "__" + tool.name)
                            alias = raw_alias[:55] + "_" + hashlib.sha256(raw_alias.encode()).hexdigest()[:8] if len(raw_alias) > 64 else raw_alias
                            discovered.append({"alias": alias, "remote_alias": f"{server.name}.{tool.name}", "description": str(tool.description or "Approved read-only MCP tool")[:300], "schema": tool.inputSchema, "roles": sorted(server.roles - {"admin"})})
                        if not page.nextCursor:
                            break
                        cursor = page.nextCursor
            except Exception:
                self._states[server.name] = "unavailable"
                continue
        self._catalog, self._catalog_at = discovered, time.monotonic()
        return list(discovered)

    def info(self) -> dict[str, Any]:
        return {"servers": [{"name": server.name, "transport": server.transport, "allowed_tools": sorted(server.allowed_tools), "roles": sorted(server.roles), "read_only": server.read_only, "status": self._states[server.name]} for server in self.servers.values()], "discovered_tools": [tool["alias"] for tool in self._catalog]}

    async def call(self, role: str, alias: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if "." not in alias:
            raise PermissionError("MCP tool alias must include its server")
        server_name, tool_name = alias.split(".", 1)
        server = self.servers.get(server_name)
        if server is None or role not in server.roles or tool_name not in server.allowed_tools:
            raise PermissionError("MCP tool is not allowlisted for this role")
        async with AsyncExitStack() as stack:
            if server.transport == "streamable_http":
                headers = {name: os.environ[variable] for name, variable in server.headers_env if variable in os.environ}
                client = await stack.enter_async_context(httpx.AsyncClient(timeout=10, follow_redirects=False, headers=headers))
                streams = await stack.enter_async_context(streamable_http_client(server.url, http_client=client))
                read, write = streams[:2]
            else:
                env = {name: os.environ[name] for name in server.env_allowlist if name in os.environ}
                read, write = await stack.enter_async_context(stdio_client(StdioServerParameters(command=server.command, args=list(server.args), env=env)))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            cursor = None
            found = None
            for _ in range(10):
                page = await session.list_tools(cursor=cursor)
                found = next((tool for tool in page.tools if tool.name == tool_name), None)
                if found or not page.nextCursor:
                    break
                cursor = page.nextCursor
            if found is None:
                raise ValueError("Approved MCP tool is absent from the server catalog")
            hints = found.annotations
            if hints is None or hints.readOnlyHint is not True or hints.destructiveHint is True:
                raise PermissionError("MCP tool lacks an affirmative read-only annotation")
            errors = list(Draft202012Validator(found.inputSchema).iter_errors(arguments))
            if errors:
                raise ValueError(f"Invalid MCP arguments: {errors[0].message}")
            result = await session.call_tool(tool_name, arguments, read_timeout_seconds=timedelta(seconds=10))
            if result.isError:
                raise RuntimeError("MCP tool reported an execution error")
            output = result.model_dump(mode="json")
            encoded = json.dumps(output)
            if len(encoded) > 12000:
                raise ValueError("MCP output exceeds the configured bound")
            return output
