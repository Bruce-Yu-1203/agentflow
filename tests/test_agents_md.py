from pathlib import Path
import unittest


class AgentsInstructionsTest(unittest.TestCase):
    def test_agents_md_contains_required_instructions(self):
        expected = [
            "**Matters need attentions**",
            "1. You MUST create a git commit after every modification to trace the project, commits should follow conventional commit standard.",
            "2. You MUST create or modify related test files after every modification, and ensure every test and validation passed before giving them to user.",
            "3. All the comments are written in English",
        ]
        content = (Path(__file__).resolve().parents[1] / "AGENTS.md").read_text().splitlines()
        self.assertEqual(content, [expected[0], "", *expected[1:]])


if __name__ == "__main__":
    unittest.main()
