from pathlib import Path
import re
import unittest


DOCS = Path(__file__).resolve().parents[1] / "docs"


class DocumentationTest(unittest.TestCase):
    def test_requirement_ids_are_unique_and_mapped_to_technical_design(self):
        requirements = (DOCS / "requirements.md").read_text(encoding="utf-8")
        technical = (DOCS / "technical-design.md").read_text(encoding="utf-8")
        declared = re.findall(r"^\| (FR-\d{2}) \| P[01] \|", requirements, re.MULTILINE)
        mapped = re.findall(r"^\| (FR-\d{2}) \|", technical, re.MULTILINE)
        self.assertTrue(declared)
        self.assertEqual(len(declared), len(set(declared)))
        self.assertEqual(set(declared), set(mapped))

    def test_relative_document_links_resolve(self):
        for document in DOCS.glob("*.md"):
            content = document.read_text(encoding="utf-8")
            for target in re.findall(r"\]\(([^)]+\.md)\)", content):
                with self.subTest(document=document.name, target=target):
                    self.assertTrue((document.parent / target).is_file())


if __name__ == "__main__":
    unittest.main()
