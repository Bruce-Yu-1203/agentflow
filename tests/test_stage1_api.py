import sys
from pathlib import Path
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "python"))

from fastapi.testclient import TestClient

from agentflow.api.app import create_app
from agentflow.config import Settings


class StageOneAPITest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(Settings(environment="test")))

    def test_health_and_contract_paths(self):
        self.assertEqual(self.client.get("/health").json()["status"], "ok")
        schema = self.client.get("/openapi.json").json()
        self.assertIn("ChatRequest", schema["components"]["schemas"])
        self.assertIn("ChatResponse", schema["components"]["schemas"])
        for path in (
            "/chat", "/search", "/knowledge/add", "/knowledge/upload",
            "/knowledge/stats", "/skills", "/skills/reload", "/monitor",
            "/metrics", "/eval/run", "/integrations/embedding",
            "/integrations/mcp", "/integrations/mcp/call",
        ):
            with self.subTest(path=path):
                self.assertIn(path, schema["paths"])

    def test_unimplemented_capability_is_explicit(self):
        response = self.client.post("/chat", json={"message": "Hello"})
        self.assertEqual(response.status_code, 503)

    def test_invalid_message_rejected_at_contract_boundary(self):
        response = self.client.post("/chat", json={"message": ""})
        self.assertEqual(response.status_code, 422)

    def test_production_requires_credentials_and_disallows_demo_seed(self):
        self.assertEqual(Settings().chroma_port, 8001)
        with self.assertRaisesRegex(ValueError, "MODEL_API_KEY"):
            Settings(environment="production").validate()
        with self.assertRaisesRegex(ValueError, "Demo knowledge"):
            Settings(environment="production", model_api_key="key", api_tokens="token", seed_demo_docs=True).validate()


if __name__ == "__main__":
    unittest.main()
