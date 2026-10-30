import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_FILE = ROOT / "data" / "knowledge" / "demo_knowledge.json"
SKILLS_DIR = ROOT / "skills"


class ContentAssetsTest(unittest.TestCase):
    def test_demo_knowledge_uses_upload_contract_and_stable_unique_ids(self):
        documents = json.loads(KNOWLEDGE_FILE.read_text(encoding="utf-8"))
        expected_ids = {
            "demo-refund-policy",
            "demo-order-status",
            "demo-account-security",
            "demo-technical-troubleshooting",
            "demo-membership-points",
            "demo-delivery-service",
        }
        self.assertIsInstance(documents, list)
        self.assertEqual({document["document_id"] for document in documents}, expected_ids)
        self.assertEqual(len(documents), len(expected_ids))
        for document in documents:
            with self.subTest(document=document["document_id"]):
                self.assertEqual(set(document), {"document_id", "title", "content"})
                self.assertRegex(document["document_id"], r"^demo-[a-z-]+$")
                self.assertTrue(document["title"].strip())
                self.assertGreater(len(document["content"].strip()), 100)
                self.assertIn("sample", document["content"].lower())

    def test_skills_are_loadable_and_scoped_to_their_roles(self):
        expected = {
            "general_customer_service": ("general", "order"),
            "technical_support": ("technical", "401"),
            "billing_support": ("billing", "refund"),
        }
        paths = sorted(SKILLS_DIR.glob("*/SKILL.md"))
        self.assertEqual({path.parent.name for path in paths}, set(expected))
        for path in paths:
            with self.subTest(skill=path.parent.name):
                content = path.read_text(encoding="utf-8")
                sections = content.split("---", 2)
                self.assertEqual(len(sections), 3)
                self.assertFalse(sections[0].strip())
                fields = dict(line.split(":", 1) for line in sections[1].strip().splitlines())
                fields = {key.strip(): value.strip() for key, value in fields.items()}
                self.assertEqual(set(fields), {"name", "description", "keywords", "agents", "enabled"})
                role, keyword = expected[path.parent.name]
                self.assertEqual(fields["agents"], role)
                self.assertEqual(fields["enabled"], "true")
                self.assertIn(keyword, [item.strip() for item in fields["keywords"].split(",")])
                self.assertTrue(fields["name"])
                self.assertTrue(fields["description"])
                self.assertIn("## Workflow", sections[2])
                self.assertIn("## Escalation", sections[2])

    def test_content_assets_are_english_and_use_agentflow_identity(self):
        paths = [KNOWLEDGE_FILE, *SKILLS_DIR.rglob("*.md"), ROOT / "data" / "knowledge" / "README.md"]
        for path in paths:
            with self.subTest(path=path.relative_to(ROOT)):
                content = path.read_text(encoding="utf-8")
                self.assertNotRegex(content, r"[\u3400-\u9fff]")
                self.assertNotRegex(content, r"(?i)echomind|\bjava\b|spring boot|langchain4j")


if __name__ == "__main__":
    unittest.main()
