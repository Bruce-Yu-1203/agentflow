"""Validates the shipped evaluation benchmark and its API request format."""

import json
from pathlib import Path
import unittest

from agentflow.api.contracts import EvaluationRequest
from agentflow.core.intent_recognizer import IntentCategory


ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "data/evaluation"


class EvaluationDatasetTests(unittest.TestCase):
    def load_split(self, split: str) -> dict:
        return json.loads((DATASET_DIR / f"support_{split}.json").read_text(encoding="utf-8"))

    def test_splits_are_balanced_disjoint_and_match_runtime_intents(self):
        splits = {name: self.load_split(name) for name in ("train", "validation", "test")}
        expected_labels = {intent.value for intent in IntentCategory}
        seen_messages: set[str] = set()
        for split_name, payload in splits.items():
            with self.subTest(split=split_name):
                EvaluationRequest.model_validate(payload)
                cases = payload["intent_cases"]
                counts = {label: sum(case["expected_intent"] == label for case in cases) for label in expected_labels}
                self.assertEqual(set(counts.values()), {10 if split_name == "train" else 5})
                for case in cases:
                    self.assertTrue(case["message"].strip())
                    self.assertNotIn(case["message"], seen_messages)
                    seen_messages.add(case["message"])
        self.assertEqual(len(seen_messages), 380)

    def test_rag_and_dialogue_annotations_match_available_contracts(self):
        documents = json.loads((ROOT / "data/knowledge/demo_knowledge.json").read_text(encoding="utf-8"))
        valid_document_ids = {document["document_id"] for document in documents}
        for split_name, expected_count in (("validation", 30), ("test", 30)):
            payload = self.load_split(split_name)
            with self.subTest(split=split_name):
                self.assertEqual(len(payload["rag_cases"]), expected_count)
                self.assertEqual(len(payload["dialog_cases"]), 10)
                self.assertTrue(all(set(case["relevant_document_ids"]) <= valid_document_ids for case in payload["rag_cases"]))
                per_document = {
                    document_id: sum(document_id in case["relevant_document_ids"] for case in payload["rag_cases"])
                    for document_id in valid_document_ids
                }
                self.assertEqual(set(per_document.values()), {5})
                self.assertTrue(all(case.get("turns") and case.get("expected_intent") and case.get("expected_agent") for case in payload["dialog_cases"]))
                EvaluationRequest.model_validate(payload)

    def test_dataset_readme_marks_synthetic_scope_and_documents_how_to_run(self):
        readme = (DATASET_DIR / "README.md").read_text(encoding="utf-8")
        self.assertIn("realistic synthetic examples", readme)
        self.assertIn("support_test.json", readme)
        self.assertIn("/api/knowledge/upload", readme)
        self.assertIn("keep the test split untouched", readme)


if __name__ == "__main__":
    unittest.main()
