"""Stage 6 endpoint, CLI, and production configuration checks."""

from io import StringIO
import unittest

from fastapi.testclient import TestClient

from agentflow.agents.agent_orchestrator import Orchestrator
from agentflow.api.app import create_app
from agentflow.cli import run_chat
from agentflow.config import Settings
from agentflow.core.intent_recognizer import IntentRecognizer
from agentflow.core.model import ModelReply
from agentflow.mcp.knowledge_base import KnowledgeStore
import chromadb


class FakeModel:
    async def complete(self, **kwargs):
        if kwargs["stage"] == "intent":
            return ModelReply(text='{"intent":"greeting","confidence":0.99}')
        return ModelReply(text="Hello from AgentFlow")


class Stage6Tests(unittest.TestCase):
    def test_embedding_endpoints(self):
        model = FakeModel()
        orchestrator = Orchestrator(IntentRecognizer(model, "test"), model, "test")
        client = TestClient(create_app(Settings(environment="test"), orchestrator))
        self.assertEqual(client.get("/integrations/embedding").status_code, 200)
        self.assertIn("source", client.post("/integrations/embedding/check", json={"message": "Hello"}).json())
        self.assertEqual(client.post("/integrations/embedding/check", json={"message": ""}).status_code, 422)
        self.assertEqual(client.get("/health").json()["status"], "ok")

    def test_cli_conversation_and_new_command(self):
        responses = []
        inputs = iter(["Hello", "Follow up", "/new", "Another topic", "/exit"])
        def send(url, body, headers):
            responses.append(body)
            return {"conv_id": "conversation-1" if len(responses) < 3 else "conversation-2", "response": "Answer", "status": "success"}
        output = StringIO()
        code = run_chat("http://localhost:8000", input_fn=lambda _: next(inputs), output=output, send=send)
        self.assertEqual(code, 0)
        self.assertNotIn("conv_id", responses[0])
        self.assertEqual(responses[1]["conv_id"], "conversation-1")
        self.assertNotIn("conv_id", responses[2])
        self.assertIn("Goodbye", output.getvalue())

    def test_production_configuration_rejects_bad_token_map(self):
        with self.assertRaisesRegex(ValueError, "JSON token map"):
            Settings(environment="production", model_api_key="key", api_tokens="token").validate()
        with self.assertRaisesRegex(ValueError, "EMBEDDING_API_KEY"):
            Settings(environment="production", model_api_key="key", api_tokens='{"token":{"user_id":"u","role":"admin"}}', embedding_provider="online").validate()

    def test_public_contract_has_no_missing_paths(self):
        schema = TestClient(create_app(Settings(environment="test"))).get("/openapi.json").json()
        for path in ("/chat", "/search", "/knowledge/add", "/knowledge/upload", "/knowledge/stats", "/skills", "/skills/reload", "/trace/tool/{request_id}", "/trace/tools", "/monitor", "/metrics", "/eval/run", "/eval/jobs/{job_id}", "/integrations/embedding", "/integrations/embedding/check", "/integrations/mcp", "/integrations/mcp/call"):
            self.assertIn(path, schema["paths"])

    def test_local_mcp_endpoint_initializes(self):
        app = create_app(Settings(environment="test"), knowledge=KnowledgeStore(chromadb.EphemeralClient()))
        with TestClient(app, base_url="http://localhost:8000") as client:
            response = client.post("/mcp/", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}}, headers={"Accept": "application/json, text/event-stream", "Content-Type": "application/json"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["result"]["serverInfo"]["name"], "AgentFlow Knowledge")

    def test_failed_agent_returns_service_error(self):
        class EmptyModel(FakeModel):
            async def complete(self, **kwargs):
                if kwargs["stage"] == "intent":
                    return ModelReply(text='{"intent":"query","confidence":0.99}')
                return ModelReply(text="")
        model = EmptyModel()
        client = TestClient(create_app(Settings(environment="test"), Orchestrator(IntentRecognizer(model, "test", embedding_enabled=False), model, "test")))
        response = client.post("/chat", json={"message": "What is the policy?"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "failed")

    def test_console_origin_is_allowed(self):
        client = TestClient(create_app(Settings(environment="test")))
        response = client.options("/chat", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization,content-type"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5173")


if __name__ == "__main__":
    unittest.main()
