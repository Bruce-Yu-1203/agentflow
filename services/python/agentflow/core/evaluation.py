"""Bounded asynchronous evaluation with suite-compatible baselines."""

import asyncio
from collections import OrderedDict
import hashlib
import json
import math
from typing import Any
from uuid import uuid4

from agentflow.agents.orchestrator import Orchestrator
from agentflow.core.intent import IntentRecognizer
from agentflow.core.model import ModelClient


class EvaluationQueueFull(Exception):
    pass


class EvaluationService:
    def __init__(self, model: ModelClient | None, model_name: str, knowledge: Any | None = None):
        self.model, self.model_name = model, model_name
        self.knowledge = knowledge
        self.jobs: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self.baselines: dict[str, dict[str, Any]] = {}
        self._gate = asyncio.Semaphore(1)
        self._unfinished = 0

    def submit(self, cases: dict[str, Any]) -> dict[str, Any]:
        if self._unfinished >= 8:
            raise EvaluationQueueFull("Evaluation queue is full")
        intent_cases = cases.get("intent_cases") or []
        dialog_cases = cases.get("dialog_cases") or []
        rag_cases = cases.get("rag_cases") or []
        if not intent_cases and not dialog_cases and not rag_cases:
            raise ValueError("At least one evaluation case is required")
        job_id = str(uuid4())
        job = {"job_id": job_id, "status": "queued", "completed": 0, "total": len(intent_cases) + len(dialog_cases) + len(rag_cases), "result": None, "error": None}
        self.jobs[job_id] = job
        while len(self.jobs) > 50:
            self.jobs.popitem(last=False)
        self._unfinished += 1
        asyncio.create_task(self._run(job, cases))
        return dict(job)

    def get(self, job_id: str) -> dict[str, Any] | None:
        job = self.jobs.get(job_id)
        return dict(job) if job else None

    async def _run(self, job: dict[str, Any], cases: dict[str, Any]) -> None:
        try:
            async with self._gate:
                job["status"] = "running"
                async with asyncio.timeout(1800):
                    job["result"] = await self._evaluate(job, cases)
                job["status"] = "completed"
        except asyncio.CancelledError:
            job["status"] = "cancelled"
        except Exception as exc:
            job["status"] = "failed"
            job["error"] = str(exc)[:200]
        finally:
            self._unfinished -= 1

    async def _evaluate(self, job: dict[str, Any], cases: dict[str, Any]) -> dict[str, Any]:
        suite_id = hashlib.sha256(json.dumps([cases, self.model_name, "judge-v1", 0.75], sort_keys=True).encode()).hexdigest()
        recognizer = IntentRecognizer(self.model, self.model_name)
        orchestrator = Orchestrator(recognizer, self.model, self.model_name)
        intent_hits = 0
        intent_total = 0
        intent_pairs: list[tuple[str, str]] = []
        dialog_scores: list[float] = []
        judge_errors = 0
        assertions_passed = 0
        assertions_total = 0
        for case in cases.get("intent_cases") or []:
            result = await recognizer.recognize(case["message"], case.get("context", {}).get("history", []) if case.get("context") else [])
            intent_hits += result.intent.value == case["expected_intent"]
            intent_total += 1
            intent_pairs.append((case["expected_intent"], result.intent.value))
            job["completed"] += 1
        for case in cases.get("dialog_cases") or []:
            turns = case.get("turns") or [case.get("question", "")]
            if not turns or not all(turns):
                judge_errors += 1
                job["completed"] += 1
                continue
            history: list[dict[str, str]] = []
            result = None
            for turn in turns:
                result = await orchestrator.run(turn, history=history)
                history.extend([{"role": "user", "content": turn}, {"role": "assistant", "content": result.response}])
            assert result is not None
            for expected, actual in ((case.get("expected_agent"), result.route.primary), (case.get("expected_intent"), result.intent.intent.value)):
                if expected:
                    assertions_total += 1
                    assertions_passed += expected == actual
            if case.get("required_tools"):
                assertions_total += 1
                assertions_passed += set(case["required_tools"]) <= set(result.tools_used)
            if case.get("expected_entities"):
                assertions_total += 1
                assertions_passed += all(result.intent.entities.get(key) == value for key, value in case["expected_entities"].items())
            score = await self._judge(case, result.response)
            if score is None:
                judge_errors += 1
            else:
                dialog_scores.append(score)
            job["completed"] += 1
        mean_score = sum(dialog_scores) / len(dialog_scores) if dialog_scores else None
        rag_recalls: list[float] = []
        rag_precisions: list[float] = []
        rag_errors = 0
        for case in cases.get("rag_cases") or []:
            if self.knowledge is None:
                rag_errors += 1
            else:
                try:
                    hits = await self.knowledge.search(case["query"], case.get("top_k", 5))
                    predicted = [hit["document_id"] for hit in hits]
                    relevant = set(case["relevant_document_ids"])
                    rag_recalls.append(len(relevant.intersection(predicted)) / len(relevant))
                    rag_precisions.append(sum(item in relevant for item in predicted) / len(predicted) if predicted else 0.0)
                except Exception:
                    rag_errors += 1
            job["completed"] += 1
        labels = {label for pair in intent_pairs for label in pair}
        f1_values = []
        for label in labels:
            tp = sum(expected == label and predicted == label for expected, predicted in intent_pairs)
            fp = sum(expected != label and predicted == label for expected, predicted in intent_pairs)
            fn = sum(expected == label and predicted != label for expected, predicted in intent_pairs)
            f1_values.append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0)
        complete = judge_errors == 0 and rag_errors == 0
        report = {"suite_id": suite_id, "complete": complete, "intent_accuracy": intent_hits / intent_total if intent_total else None, "intent_macro_f1": sum(f1_values) / len(f1_values) if f1_values else None, "intent_count": intent_total, "dialog_score": mean_score, "valid_dialog_count": len(dialog_scores), "dialog_pass_rate": sum(score >= 0.75 for score in dialog_scores) / len(dialog_scores) if dialog_scores else None, "judge_errors": judge_errors, "rag_recall_at_k": sum(rag_recalls) / len(rag_recalls) if rag_recalls else None, "rag_evidence_precision": sum(rag_precisions) / len(rag_precisions) if rag_precisions else None, "rag_errors": rag_errors, "assertion_accuracy": assertions_passed / assertions_total if assertions_total else None, "threshold": 0.75}
        baseline = self.baselines.get(suite_id)
        report["regressed"] = bool(baseline and mean_score is not None and baseline.get("dialog_score") is not None and mean_score < baseline["dialog_score"] - 0.05)
        if complete and not report["regressed"]:
            self.baselines[suite_id] = report.copy()
        return report

    async def _judge(self, case: dict[str, Any], response: str) -> float | None:
        if self.model is None:
            return None
        try:
            reply = await self.model.complete(stage="judge", model=self.model_name, system="Score relevance, accuracy, completeness, and helpfulness from 0 to 1. Return only JSON with those four numeric fields. Do not reward unsupported claims.", messages=[{"role": "user", "content": json.dumps({"case": case, "response": response})}], max_tokens=200, temperature=0, timeout=15)
            if reply.truncated:
                return None
            scores = json.loads(reply.text)
            values = [scores[key] for key in ("relevance", "accuracy", "completeness", "helpfulness")]
            if any(type(value) not in {int, float} or not math.isfinite(value) or not 0 <= value <= 1 for value in values):
                return None
            return sum(values) / 4
        except Exception:
            return None
