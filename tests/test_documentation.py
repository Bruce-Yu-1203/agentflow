from pathlib import Path
import re
import unittest


DOCS = Path(__file__).resolve().parents[1] / "docs"


class DocumentationTest(unittest.TestCase):
    def test_product_documents_are_english_and_do_not_name_the_source_project(self):
        for document in DOCS.glob("*.md"):
            content = document.read_text(encoding="utf-8")
            with self.subTest(document=document.name):
                self.assertNotIn("echomind", content.lower())
                self.assertNotRegex(content, r"(?i)\bjava\b|spring boot|langchain4j")
                self.assertNotRegex(content, r"[\u3400-\u9fff]")

    def test_requirement_ids_are_unique_and_mapped_to_technical_design(self):
        requirements = (DOCS / "requirements.md").read_text(encoding="utf-8")
        technical = (DOCS / "technical-design.md").read_text(encoding="utf-8")
        matrix = (DOCS / "implementation-matrix.md").read_text(encoding="utf-8")
        declared = re.findall(r"^\| (FR-\d{2}) \| P[01] \|", requirements, re.MULTILINE)
        mapped = re.findall(r"^\| (FR-\d{2}) \|", technical, re.MULTILINE)
        owned = re.findall(r"^\| (FR-\d{2}) \|", matrix, re.MULTILINE)
        self.assertTrue(declared)
        self.assertEqual(len(declared), len(set(declared)))
        self.assertEqual(set(declared), set(mapped))
        self.assertEqual(set(declared), set(owned))

    def test_full_reproduction_roadmap_has_contiguous_stages_and_all_surfaces(self):
        technical = (DOCS / "technical-design.md").read_text(encoding="utf-8")
        stages = [int(value) for value in re.findall(r"^### Stage (\d+) —", technical, re.MULTILINE)]
        self.assertEqual(stages, list(range(9)))
        roadmap = technical.split("## 10. Development Roadmap for Complete Reproduction", 1)[1]
        for surface in ("Python", "web console", "Compose"):
            with self.subTest(surface=surface):
                self.assertIn(surface, roadmap)

    def test_implementation_blueprint_covers_each_python_and_web_subsystem(self):
        technical = (DOCS / "technical-design.md").read_text(encoding="utf-8")
        blueprint = technical.split("## 12. Concrete Implementation Blueprint", 1)[1]
        sections = re.findall(r"^### 12\.(\d+) ", blueprint, re.MULTILINE)
        self.assertEqual(sections, [str(number) for number in range(1, 9)])
        for term in (
            "Intent recognition", "Router", "Role tools", "RAG", "Conversation memory",
            "Skills", "MCP", "Evaluation", "monitoring", "web console",
            "retry_safe", "client_request_id", "embedding_source",
        ):
            with self.subTest(term=term):
                self.assertIn(term, blueprint)

    def test_relative_document_links_resolve(self):
        for document in DOCS.glob("*.md"):
            content = document.read_text(encoding="utf-8")
            for target in re.findall(r"\]\(([^)]+\.md)\)", content):
                with self.subTest(document=document.name, target=target):
                    self.assertTrue((document.parent / target).is_file())


if __name__ == "__main__":
    unittest.main()
