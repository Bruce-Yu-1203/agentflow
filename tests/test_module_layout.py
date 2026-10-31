"""Checks for the runtime's responsibility-based module boundaries."""

import importlib
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1] / "services/python/agentflow"


class ModuleLayoutTests(unittest.TestCase):
    def test_each_runtime_responsibility_has_an_owner(self):
        owners = {
            "core.intent_recognizer": "IntentRecognizer",
            "core.skill_loader": "SkillManager",
            "agents.agent_orchestrator": "Orchestrator",
            "agents.tools": "create_handoff_summary",
            "mcp.knowledge_base": "KnowledgeStore",
            "mcp.retrieval": "RetrievalPipeline",
            "mcp.tool_manager": "ToolRegistry",
            "mcp.client": "MCPManager",
            "mcp.server": "build_mcp_server",
            "memory.conversation_memory": "ConversationStore",
            "memory.long_term": "LongTermMemory",
            "evaluation.evaluator": "EvaluationService",
        }
        for module_name, symbol_name in owners.items():
            with self.subTest(module=module_name):
                module = importlib.import_module(f"agentflow.{module_name}")
                self.assertEqual(getattr(module, symbol_name).__module__, module.__name__)
                self.assertTrue((ROOT / (module_name.replace(".", "/") + ".py")).is_file())

    def test_previous_catch_all_modules_are_removed(self):
        previous = (
            "core/intent.py", "core/skills.py", "agents/orchestrator.py",
            "core/knowledge.py", "core/retrieval.py", "core/mcp.py",
            "core/mcp_server.py", "core/memory.py", "core/longterm.py",
            "core/evaluation.py",
        )
        for path in previous:
            with self.subTest(path=path):
                self.assertFalse((ROOT / path).exists())


if __name__ == "__main__":
    unittest.main()
