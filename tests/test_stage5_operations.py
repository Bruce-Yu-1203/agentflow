"""Stage 5 redaction, health, metrics, and evaluation integrity."""

import asyncio
import unittest

from fastapi.testclient import TestClient

from agentflow.api.app import create_app
from agentflow.config import Settings
from agentflow.core.evaluation import EvaluationService
from agentflow.core.model import ModelReply
from agentflow.core.operations import Operations, redact


class EvalModel:
    async def complete(self, **kwargs):
        if kwargs["stage"] == "intent":
            return ModelReply(text='{"intent":"greeting","confidence":0.99}')
        if kwargs["stage"] == "judge":
            return ModelReply(text="invalid judge output")
        return ModelReply(text="Hello")


class Stage5Tests(unittest.TestCase):
    def test_redaction_and_metrics(self):
        operations = Operations()
        operations.record("request-1", "success", 120, "general", [{"tool_name": "example", "success": False, "error": "Bearer secret-token"}])
        trace = operations.one_trace("request-1")
        self.assertNotIn("secret-token", str(trace))
        self.assertIn("agentflow_chat_total", operations.metrics())
        self.assertEqual(redact({"api_key": "secret"})["api_key"], "[REDACTED]")

    def test_monitor_cooldown_is_role_specific(self):
        operations = Operations()
        for index in range(5):
            operations.record(str(index), "failed", 5000, "technical", [])
        self.assertIn("technical", operations.unavailable_roles())
        self.assertNotIn("billing", operations.unavailable_roles())

    def test_invalid_judge_cannot_replace_baseline(self):
        async def check():
            service = EvaluationService(EvalModel(), "test")
            job = {"completed": 0}
            report = await service._evaluate(job, {"intent_cases": [], "dialog_cases": [{"question": "Hello", "reference_answer": "Hello"}]})
            self.assertFalse(report["complete"])
            self.assertEqual(report["judge_errors"], 1)
            self.assertNotIn(report["suite_id"], service.baselines)
        asyncio.run(check())

    def test_operations_api(self):
        client = TestClient(create_app(Settings(environment="test")))
        self.assertEqual(client.get("/monitor").status_code, 200)
        self.assertIn("agentflow_chat_total", client.get("/metrics").text)
        self.assertEqual(client.get("/trace/tool/missing").json()["found"], False)
        self.assertEqual(client.post("/eval/run", json={}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
