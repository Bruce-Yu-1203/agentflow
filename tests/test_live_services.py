"""Optional integration checks against the Compose Redis and Chroma services."""

import asyncio
import os
import unittest
from uuid import uuid4

import chromadb
from fastapi.testclient import TestClient
from redis.asyncio import Redis

from agentflow.api.app import create_app
from agentflow.config import Settings
from agentflow.mcp.knowledge_base import KnowledgeStore
from agentflow.memory.conversation_memory import ConversationStore


@unittest.skipUnless(os.getenv("AGENTFLOW_LIVE_SERVICES") == "1", "Live services are optional")
class LiveServicesTests(unittest.TestCase):
    def test_health_knowledge_and_receipt(self):
        with TestClient(create_app(Settings(environment="development"))) as client:
            self.assertEqual(client.get("/health").status_code, 200)
        document_id = "agentflow-test-" + uuid4().hex
        chroma = chromadb.HttpClient(host="localhost", port=8001)
        knowledge = KnowledgeStore(chroma)
        async def check():
            try:
                await knowledge.add([{"document_id": document_id, "title": "Test policy", "content": "A test policy requires a reference number."}])
                self.assertTrue(knowledge.collection.get(where={"document_id": document_id})["ids"])
                redis = Redis.from_url("redis://localhost:6379/0", decode_responses=True)
                store = ConversationStore(redis)
                conv_id = uuid4().hex
                request_id = uuid4().hex
                try:
                    async with await store.acquire("integration-user", conv_id, request_id) as lease:
                        context = await store.context("integration-user", conv_id, request_id)
                        await store.commit(lease, "integration-user", conv_id, request_id, "Hello", {"status": "success", "response": "Hi"}, context, {}, [])
                    receipt = await store.receipt("integration-user", conv_id, request_id, "Hello")
                    self.assertEqual(receipt["response"]["response"], "Hi")
                finally:
                    keys = store.keys("integration-user", conv_id, request_id)
                    await redis.delete(*keys)
                    await redis.aclose()
            finally:
                ids = knowledge.collection.get(where={"document_id": document_id})["ids"]
                if ids:
                    knowledge.collection.delete(ids=ids)
        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
