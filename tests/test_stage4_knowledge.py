"""Stage 4 knowledge, Skill, and MCP boundaries."""

import asyncio
from pathlib import Path
import tempfile
import unittest

import chromadb
from fastapi.testclient import TestClient

from agentflow.api.app import create_app
from agentflow.config import Settings
from agentflow.mcp.knowledge_base import KnowledgeStore, chunk_text, parse_upload
from agentflow.mcp.client import MCPManager
from agentflow.core.skill_loader import SkillManager
from agentflow.mcp.retrieval import RetrievalPipeline
from agentflow.mcp.tool_manager import ToolRegistry, ToolSpec


class Stage4Tests(unittest.TestCase):
    def setUp(self):
        chroma = chromadb.EphemeralClient()
        try:
            chroma.delete_collection("knowledge_base")
        except Exception:
            pass
        self.knowledge = KnowledgeStore(chroma)

    def test_reimport_replaces_stale_chunks(self):
        async def check():
            await self.knowledge.add([{"document_id": "policy-1", "title": "Policy", "content": "Refunds take seven days. " * 40}])
            self.assertGreater(await self.knowledge.count(), 1)
            await self.knowledge.add([{"document_id": "policy-1", "title": "Updated", "content": "Refunds require order verification."}])
            self.assertEqual(await self.knowledge.count(), 1)
            hit = (await self.knowledge.search("refund verification"))[0]
            self.assertEqual(hit["title"], "Updated")
            self.assertEqual(hit["document_id"], "policy-1")
        asyncio.run(check())

    def test_invalid_batch_does_not_remove_existing_document(self):
        async def check():
            await self.knowledge.add([{"document_id": "stable", "title": "Stable", "content": "Keep this policy."}])
            with self.assertRaises(ValueError):
                await self.knowledge.add([{"document_id": "stable", "title": "Changed", "content": "Replace it."}, {"title": "Invalid", "content": ""}])
            hit = (await self.knowledge.search("policy"))[0]
            self.assertEqual(hit["title"], "Stable")
        asyncio.run(check())

    def test_chunk_boundaries_and_upload_validation(self):
        self.assertTrue(all(len(chunk) <= 500 for chunk in chunk_text("A" * 1200)))
        self.assertEqual(len(parse_upload("guide.md", b"English guidance")), 1)
        with self.assertRaises(ValueError):
            parse_upload("guide.exe", b"bad")

    def test_skill_reload_and_scoping(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "billing.md"
            path.write_text("---\nname: Billing\nkeywords: refund\nagents: billing\n---\nCheck the policy.")
            manager = SkillManager(directory)
            self.assertIn("Check the policy", manager.matching("billing", "refund please"))
            self.assertEqual(manager.matching("technical", "refund please"), "")
            path.write_text("---\nname: Billing\nkeywords: invoice\nagents: billing\n---\nAsk for an invoice ID.")
            manager.reload()
            self.assertEqual(manager.matching("billing", "refund please"), "")

    def test_knowledge_api_and_mcp_allowlist(self):
        client = TestClient(create_app(Settings(environment="test"), knowledge=self.knowledge))
        added = client.post("/knowledge/add", json={"documents": [{"document_id": "x", "title": "Guide", "content": "The account reset process requires email verification."}]})
        self.assertEqual(added.status_code, 200)
        self.assertEqual(client.get("/knowledge/stats").json()["total_chunks"], 1)
        self.assertEqual(len(client.post("/search?query=account%20reset").json()["results"]), 1)
        self.assertEqual(client.get("/integrations/mcp").json()["servers"], [])
        self.assertEqual(client.post("/integrations/mcp/call", json={"tool_name": "unknown.tool"}).status_code, 403)

    def test_mcp_invalid_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "servers.json"
            path.write_text('[{"name":"one","transport":"streamable_http","url":"https://user:password@example.com/mcp","roles":["admin"]}]')
            with self.assertRaises(ValueError):
                MCPManager(str(path))
            path.write_text('[{"name":"one","transport":"streamable_http","url":"https://example.com/mcp","roles":["admin"],"headers_env":{"Authorization":"bad-variable"}}]')
            with self.assertRaisesRegex(ValueError, "headers_env"):
                MCPManager(str(path))

    def test_retrieval_cache_invalidates_on_write(self):
        async def check():
            pipeline = RetrievalPipeline(self.knowledge, None, "test")
            await self.knowledge.add([{"document_id": "policy", "title": "Policy", "content": "Refunds need verification."}])
            first = await pipeline.search("refund", 1)
            self.assertFalse(first["cached"])
            self.assertTrue((await pipeline.search("refund", 1))["cached"])
            await self.knowledge.add([{"document_id": "policy", "title": "New policy", "content": "Refunds require a receipt."}])
            refreshed = await pipeline.search("refund", 1)
            self.assertFalse(refreshed["cached"])
            self.assertEqual(refreshed["results"][0]["title"], "New policy")
        asyncio.run(check())

    def test_tool_circuit_and_schema_failures(self):
        attempts = []
        def failing() -> dict:
            attempts.append(1)
            raise RuntimeError("Unavailable")
        registry = ToolRegistry([ToolSpec("unstable", "A failing read tool", {}, (), frozenset({"general"}), failing)])
        async def check():
            with self.assertRaises(ValueError):
                await registry.execute("general", "unstable", {"unexpected": True})
            self.assertEqual(registry._failures.get("unstable", 0), 0)
            for _ in range(5):
                with self.assertRaises(RuntimeError):
                    await registry.execute("general", "unstable", {})
            self.assertEqual(len(attempts), 5)
            with self.assertRaisesRegex(RuntimeError, "circuit is open"):
                await registry.execute("general", "unstable", {})
            self.assertEqual(len(attempts), 5)
        asyncio.run(check())

    def test_discovered_mcp_tool_obeys_role_schema(self):
        class FakeManager:
            servers = {"docs": object()}
            async def discover(self):
                return [{"alias": "mcp__docs__lookup", "remote_alias": "docs.lookup", "description": "Read a document", "schema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"], "additionalProperties": False}, "roles": ["technical"]}]
            async def call(self, role, alias, arguments):
                return {"role": role, "alias": alias, "id": arguments["id"]}
        async def check():
            registry = ToolRegistry()
            await registry.refresh_mcp(FakeManager())
            self.assertIn("mcp__docs__lookup", [item["name"] for item in registry.definitions("technical")])
            with self.assertRaises(PermissionError):
                await registry.execute("general", "mcp__docs__lookup", {"id": "a"})
            with self.assertRaises(ValueError):
                await registry.execute("technical", "mcp__docs__lookup", {"id": "a", "extra": 1})
            result = await registry.execute("technical", "mcp__docs__lookup", {"id": "a"})
            self.assertEqual(result["alias"], "docs.lookup")
        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
