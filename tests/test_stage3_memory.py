"""Stage 3 authentication, idempotency, and lease contracts."""

import asyncio
import json
import unittest

import fakeredis.aioredis
import chromadb
from fastapi.testclient import TestClient

from agentflow.agents.orchestrator import Orchestrator
from agentflow.api.app import create_app
from agentflow.config import Settings
from agentflow.core.intent import IntentRecognizer
from agentflow.core.memory import ConversationStore, LeaseLost
from agentflow.core.longterm import LongTermMemory
from agentflow.core.model import ModelReply


class CountingModel:
    def __init__(self):
        self.agent_calls = 0

    async def complete(self, **kwargs):
        if kwargs["stage"] == "intent":
            return ModelReply(text='{"intent":"query","confidence":0.95}')
        if kwargs["stage"].startswith("agent:"):
            self.agent_calls += 1
        return ModelReply(text="Here is the information available.")


class Stage3MemoryTests(unittest.TestCase):
    def setUp(self):
        self.model = CountingModel()
        recognizer = IntentRecognizer(self.model, "test", embedding_enabled=False)
        orchestrator = Orchestrator(recognizer, self.model, "test")
        self.redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        self.store = ConversationStore(self.redis)
        tokens = json.dumps({"customer-token": {"user_id": "real-user", "role": "customer"}})
        self.client = TestClient(create_app(Settings(environment="test", api_tokens=tokens), orchestrator, self.store))
        self.headers = {"Authorization": "Bearer customer-token"}

    def test_duplicate_receipt_and_changed_message(self):
        body = {"message": "What is the status?", "client_request_id": "same-id", "user_id": "spoofed"}
        first = self.client.post("/chat", json=body, headers=self.headers)
        second = self.client.post("/chat", json=body, headers=self.headers)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.json(), first.json())
        self.assertEqual(self.model.agent_calls, 1)
        changed = self.client.post("/chat", json={**body, "message": "A different request"}, headers=self.headers)
        self.assertEqual(changed.status_code, 409)

    def test_identity_required(self):
        response = self.client.post("/chat", json={"message": "Hello"})
        self.assertEqual(response.status_code, 401)

    def test_lease_loss_prevents_commit(self):
        async def check():
            async with await self.store.acquire("user", "conv", "req") as lease:
                await self.redis.delete(lease.key)
                context = await self.store.context("user", "conv", "req")
                with self.assertRaises(LeaseLost):
                    await self.store.commit(lease, "user", "conv", "req", "Hello", {"status": "success", "response": "Hi"}, context, {}, [])
                self.assertIsNone(await self.store.receipt("user", "conv", "req", "Hello"))
        asyncio.run(check())

    def test_failed_turn_does_not_enter_history(self):
        async def check():
            async with await self.store.acquire("user", "conv", "req") as lease:
                context = await self.store.context("user", "conv", "req")
                await self.store.commit(lease, "user", "conv", "req", "Hello", {"status": "failed", "response": "Unavailable", "retryable": True}, context, {}, [])
            updated = await self.store.context("user", "conv", "req")
            self.assertEqual(updated.history, [])
        asyncio.run(check())

    def test_failed_compression_preserves_raw_history(self):
        async def check():
            key = self.store.keys("user", "conv", "req")[1]
            messages = [{"role": "user", "content": f"Message {index}"} for index in range(16)]
            await self.redis.set(key, json.dumps({"history": messages, "state": {}, "summary": ""}))
            class BadModel:
                async def complete(self, **kwargs):
                    return ModelReply(text="", truncated=True)
            self.assertFalse(await self.store.compress("user", "conv", "req", BadModel(), "test"))
            self.assertEqual((await self.store.context("user", "conv", "req")).history, messages)
        asyncio.run(check())

    def test_longterm_vectors_are_user_scoped(self):
        async def check():
            client = chromadb.EphemeralClient()
            for name in ("episodic_memory", "user_profiles"):
                try:
                    client.delete_collection(name)
                except Exception:
                    pass
            memory = LongTermMemory(client)
            await memory.add_episode("alice", "conv-a", "Alice prefers email support")
            await memory.add_episode("bob", "conv-b", "Bob prefers phone support")
            self.assertEqual(await memory.relevant("alice", "conv-a", "support"), ["Alice prefers email support"])
            await memory.update_profile("alice", ["Concise replies"])
            self.assertEqual(await memory.profile("alice"), "Concise replies")
            self.assertEqual(await memory.profile("bob"), "")
        asyncio.run(check())

    def test_compression_keeps_recent_messages(self):
        async def check():
            key = self.store.keys("user", "conv", "req")[1]
            messages = [{"role": "user", "content": f"Message {index}"} for index in range(16)]
            await self.redis.set(key, json.dumps({"history": messages, "state": {}, "summary": ""}))
            class SummaryModel:
                async def complete(self, **kwargs):
                    return ModelReply(text="A concise English summary")
            summary = await self.store.compress("user", "conv", "req", SummaryModel(), "test")
            context = await self.store.context("user", "conv", "req")
            self.assertEqual(summary, "A concise English summary")
            self.assertEqual(context.history, messages[-5:])
        asyncio.run(check())

    def test_concurrent_turns_see_committed_history(self):
        async def check():
            async def first():
                async with await self.store.acquire("user", "shared", "first") as lease:
                    context = await self.store.context("user", "shared", "first")
                    await asyncio.sleep(0.02)
                    await self.store.commit(lease, "user", "shared", "first", "First", {"status": "success", "response": "One"}, context, {}, [])
            async def second():
                await asyncio.sleep(0.005)
                async with await self.store.acquire("user", "shared", "second"):
                    return await self.store.context("user", "shared", "second")
            _, context = await asyncio.gather(first(), second())
            self.assertEqual([item["content"] for item in context.history], ["First", "One"])
        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
