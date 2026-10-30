"""Stage 2 intent, routing, and tool execution contracts."""

import asyncio
import unittest

from fastapi.testclient import TestClient

from agentflow.agents.orchestrator import Orchestrator
from agentflow.agents.tools import ToolRegistry
from agentflow.api.app import create_app
from agentflow.config import Settings
from agentflow.core.intent import IntentRecognizer
from agentflow.core.model import ModelReply, ToolCall
from agentflow.core.state import extract_entities, merge_state


class FakeModel:
    def __init__(self):
        self.calls = []

    async def complete(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["stage"] == "intent":
            return ModelReply(text='{"intent":"technical_login","confidence":0.95,"reasoning":"Sign-in error"}')
        if kwargs["stage"] == "agent:technical" and len([call for call in self.calls if call["stage"] == "agent:technical"]) == 1:
            return ModelReply(tool_calls=[ToolCall("tool-1", "lookup_error_code", {"code": "401"})])
        return ModelReply(text=f"{kwargs['stage']} response")


class Stage2Tests(unittest.TestCase):
    def setUp(self):
        self.model = FakeModel()
        self.recognizer = IntentRecognizer(self.model, "test-model", embedding_enabled=False)
        self.orchestrator = Orchestrator(self.recognizer, self.model, "test-model")

    def test_mixed_route_and_tool_round(self):
        result = asyncio.run(self.orchestrator.run("Sign-in returns 401 and I was charged twice", request_id="r1"))
        self.assertEqual(result.route.primary, "technical")
        self.assertIn("billing", result.route.supporting)
        self.assertIn("lookup_error_code", result.tools_used)
        self.assertEqual(result.status, "success")

    def test_escalation_is_deterministic(self):
        result = asyncio.run(self.orchestrator.run("Emergency: connect me to a human agent", request_id="r2"))
        self.assertTrue(result.escalated)
        self.assertIn("No support ticket has been created", result.response)

    def test_tool_allowlist_and_schema(self):
        registry = ToolRegistry()
        with self.assertRaises(PermissionError):
            asyncio.run(registry.execute("general", "lookup_error_code", {"code": "401"}))
        with self.assertRaises(ValueError):
            asyncio.run(registry.execute("technical", "lookup_error_code", {"code": "401", "extra": True}))

    def test_entity_state_switch(self):
        old = merge_state(None, {"order_id": ["AB1234"], "amount": ["$12"]}, "billing", "Order #AB1234", "r1")
        new = merge_state(old, {"order_id": ["CD5678"]}, "billing", "Order #CD5678", "r2")
        self.assertEqual(new["entities"]["amount"], [])
        self.assertEqual(extract_entities("order status")["order_id"], [])

    def test_chat_contract(self):
        client = TestClient(create_app(Settings(environment="test"), self.orchestrator))
        response = client.post("/chat", json={"message": "Sign-in returns 401"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["primary_agent"], "technical")


if __name__ == "__main__":
    unittest.main()
