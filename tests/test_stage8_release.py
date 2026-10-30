"""Release package, English-content, and deployment contract checks."""

from pathlib import Path
import re
import subprocess
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from agentflow.api.app import create_app
from agentflow.config import Settings


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".py", ".js", ".mjs", ".ts", ".vue", ".md", ".json", ".yml", ".yaml", ".conf", ".sh", ".html", ".css", ".toml", ".txt", ".example"}


class Stage8ReleaseTests(unittest.TestCase):
    def test_owned_redis_connection_closes_on_api_shutdown(self):
        class FakeRedis:
            closed = False

            async def aclose(self):
                self.closed = True

        redis = FakeRedis()
        with patch("agentflow.api.app.Redis.from_url", return_value=redis):
            with TestClient(create_app(Settings(environment="development"))):
                self.assertFalse(redis.closed)
        self.assertTrue(redis.closed)

    def test_tracked_and_pending_text_is_english_and_uses_agentflow_identity(self):
        result = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True, check=True)
        paths = [ROOT / name for name in result.stdout.splitlines()]
        self.assertTrue(paths)
        legacy = "echo" + "mind"
        for path in paths:
            if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
                continue
            with self.subTest(path=path.relative_to(ROOT)):
                content = path.read_text(encoding="utf-8")
                self.assertNotRegex(content, r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af\u0400-\u052f]")
                self.assertNotIn(legacy, content.lower())
                self.assertNotIn("langchain" + "4j", content.lower())
        self.assertFalse(any(path.suffix == ".java" for path in paths))

    def test_release_stack_has_all_services_and_no_public_backend_ports(self):
        compose = (ROOT / "infra/compose.yml").read_text()
        for service in ("redis", "chroma", "api", "web", "gateway", "prometheus"):
            self.assertRegex(compose, rf"(?m)^  {service}:$")
        self.assertIn("AGENTFLOW_GATEWAY_BIND", compose)
        self.assertEqual(len(re.findall(r"(?m)^    ports:$", compose)), 1)
        gateway = (ROOT / "infra/gateway.conf").read_text()
        self.assertIn("location /api/", gateway)
        self.assertIn("location /mcp/", gateway)
        self.assertIn("proxy_buffering off", gateway)
        self.assertIn("VITE_API_BASE_URL=/api", (ROOT / "web/Dockerfile").read_text())
        self.assertRegex((ROOT / ".github/workflows/verify.yml").read_text(), r"(?m)^  release:$")

    def test_production_metrics_use_a_matching_admin_token_file(self):
        production = (ROOT / "infra/prometheus.prod.yml").read_text()
        verify = (ROOT / "infra/compose.verify.yml").read_text()
        token = (ROOT / "infra/prometheus.verify.token").read_text().strip()
        self.assertIn("credentials_file: /etc/prometheus/metrics.token", production)
        self.assertIn(f'"{token}":{{"user_id"', verify)
        self.assertIn("AGENTFLOW_ENV: production", verify)

    def test_release_runbook_and_requirement_evidence_are_complete(self):
        runbook = (ROOT / "docs/operations.md").read_text()
        evidence = (ROOT / "docs/release-validation.md").read_text()
        for topic in ("Startup", "Production", "Backup", "Restore", "Environment", "Verification"):
            self.assertIn(topic, runbook)
        for number in range(1, 15):
            self.assertRegex(evidence, rf"(?m)^\| FR-{number:02} \|")
        self.assertIn("scripts/verify_stack.sh", runbook)
        self.assertIn('project="agentflow-verify-$$"', (ROOT / "scripts/verify_stack.sh").read_text())


if __name__ == "__main__":
    unittest.main()
