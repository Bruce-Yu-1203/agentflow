"""Route a customer message to bounded, tool-aware support roles."""

import asyncio
from dataclasses import dataclass, field
import json
import re
from typing import Any

from agentflow.agents.tools import ToolRegistry, create_handoff_summary
from agentflow.core.intent import IntentRecognizer, IntentResult
from agentflow.core.model import ModelClient
from agentflow.core.state import merge_state


ROLE_PROMPTS = {
    "general": "You are the General support role. Answer broad questions, identify missing fields, and never claim access to live orders or accounts. Use only available tools. Answer in English.",
    "technical": "You are the Technical support role. Explain errors and give safe diagnostics. Do not claim that a live system was checked. Use only available tools. Answer in English.",
    "billing": "You are the Billing support role. Explain billing processes and compare customer-provided amounts. Never claim a charge, refund, or invoice was verified. Use only available tools. Answer in English.",
}
KEYWORDS = {
    "technical": ("error", "crash", "login", "sign-in", "password", "401", "500", "timeout", "bug"),
    "billing": ("refund", "charge", "charged", "payment", "invoice", "billing", "paid", "price"),
    "general": ("order", "delivery", "shipping", "question", "help", "status"),
}
SPECIALIST = {"technical": "technical", "billing": "billing", "account": "technical"}


@dataclass
class RoleResult:
    role: str
    text: str = ""
    tools_used: list[str] = field(default_factory=list)
    tool_trace: list[dict[str, Any]] = field(default_factory=list)
    status: str = "success"
    error: str | None = None
    unsafe_attempted: bool = False


@dataclass
class Route:
    primary: str
    supporting: list[str]
    scores: dict[str, float]
    reason: str


@dataclass
class OrchestratorResult:
    response: str
    intent: IntentResult
    route: Route
    status: str
    tools_used: list[str]
    tool_trace: list[dict[str, Any]]
    state: dict[str, Any]
    escalated: bool = False


class Orchestrator:
    def __init__(self, recognizer: IntentRecognizer, model: ModelClient | None, model_name: str, *, tools: ToolRegistry | None = None, skills: Any | None = None, operations: Any | None = None):
        self.recognizer = recognizer
        self.model = model
        self.model_name = model_name
        self.tools = tools or ToolRegistry()
        self.skills = skills
        self.operations = operations

    def route(self, message: str, intent: IntentResult, unavailable: set[str] | None = None) -> Route:
        if intent.urgency == "critical" or intent.intent_group == "escalation":
            return Route("escalation", [], {"escalation": 1.0}, "Urgent or explicit handoff")
        scores = {"general": 0.1, "technical": 0.0, "billing": 0.0}
        if intent.intent_group in {"query", "request", "greeting", "feedback", "complaint", "other"}:
            scores["general"] += 0.55
        target = SPECIALIST.get(intent.intent_group)
        if target:
            scores[target] += 0.75
        lowered = message.lower()
        for role, words in KEYWORDS.items():
            hits = sum(bool(re.search(r"(?<![a-z])" + re.escape(word) + r"(?![a-z])", lowered)) for word in words)
            scores[role] += min(0.35 if role == "general" else 0.45, hits * (0.12 if role == "general" else 0.18))
        if intent.entities.get("error_code"):
            scores["technical"] += 0.2
        if intent.entities.get("amount"):
            scores["billing"] += 0.15
        if intent.entities.get("order_id"):
            scores["general"] += 0.1
        available = {name: score for name, score in scores.items() if name not in (unavailable or set())}
        if not available:
            return Route("escalation", [], scores, "No automated role available")
        primary = max(available, key=lambda name: (available[name], name == "general"))
        supporting = [role for role in ("technical", "billing") if role != primary and role in available and available[role] >= max(0.45, available[primary] * 0.55)]
        if primary == "technical" and "billing" in available and re.search(r"\b(?:charged twice|double charge|payment failed)\b", lowered) and "billing" not in supporting:
            supporting.append("billing")
        if primary == "billing" and "technical" in available and re.search(r"\b(?:sign-in|login|crash|error)\b", lowered) and "technical" not in supporting:
            supporting.append("technical")
        return Route(primary, supporting, scores, "Highest eligible role scores")

    async def run(self, message: str, *, history: list[dict[str, str]] | None = None, previous_state: dict[str, Any] | None = None, request_id: str = "") -> OrchestratorResult:
        intent = await self.recognizer.recognize(message, history)
        state = merge_state(previous_state, intent.entities, intent.intent_group, message, request_id)
        route = self.route(message, intent, self.operations.unavailable_roles() if self.operations else None)
        if route.primary == "escalation":
            summary = create_handoff_summary(message, state["entities"])
            text = "I have prepared a summary for a support handoff. No support ticket has been created yet. Summary: " + summary["summary"]
            return OrchestratorResult(text, intent, route, "success", ["create_handoff_summary"], [], state, True)
        if intent.intent_group == "other" and intent.confidence < 0.5 and len(message.split()) > 2:
            return OrchestratorResult("Could you clarify what you need help with and provide any relevant reference or error code?", intent, route, "success", [], [], state)
        roles = [route.primary, *route.supporting]
        results = await asyncio.gather(*(self._run_role(role, message, intent, state, history or []) for role in roles), return_exceptions=True)
        normalized = [value if isinstance(value, RoleResult) else RoleResult(role, status="failed", error=str(value)) for role, value in zip(roles, results)]
        if normalized[0].status == "failed" and route.primary != "general" and not normalized[0].unsafe_attempted:
            fallback = await self._run_role("general", message, intent, state, history or [])
            normalized.append(fallback)
            if fallback.status != "failed":
                route.reason += "; specialist failed and General responded"
        usable = [result for result in normalized if result.text]
        if not usable:
            return OrchestratorResult("The request could not be completed. Please try again later.", intent, route, "failed", [tool for result in normalized for tool in result.tools_used], [trace for result in normalized for trace in result.tool_trace], state)
        primary_answer = next((result for result in usable if result.role == route.primary), usable[0])
        other = [result for result in usable if result is not primary_answer]
        text = primary_answer.text + ("\n\n" + "\n\n".join(f"{result.role.title()}: {result.text}" for result in other) if other else "")
        status = "partial" if any(result.status != "success" for result in normalized) else "success"
        return OrchestratorResult(text, intent, route, status, [tool for result in normalized for tool in result.tools_used], [trace for result in normalized for trace in result.tool_trace], state)

    async def _run_role(self, role: str, message: str, intent: IntentResult, state: dict[str, Any], history: list[dict[str, str]]) -> RoleResult:
        if self.model is None:
            return RoleResult(role, status="failed", error="Model service is not configured")
        result = RoleResult(role)
        system = ROLE_PROMPTS[role]
        if self.skills is not None:
            selected = self.skills.matching(role, message)
            if selected:
                system += "\n\nApproved business guidance:\n" + selected
        context = {"message": message, "intent": intent.intent.value, "entities": state["entities"], "history": history[-5:]}
        messages: list[dict[str, Any]] = [{"role": "user", "content": json.dumps(context, ensure_ascii=True)}]
        business_intent = intent.intent_group in {"query", "billing", "account", "technical", "request", "complaint"}
        definitions = [definition for definition in self.tools.definitions(role) if business_intent or definition["name"] != "search_knowledge_base"]
        try:
            for _ in range(3):
                reply = await self.model.complete(stage=f"agent:{role}", model=self.model_name, system=system, messages=messages, tools=definitions, max_tokens=1200, temperature=0.2, timeout=15)
                if reply.tool_calls:
                    messages.append({"role": "assistant", "content": reply.assistant_content or [{"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments} for call in reply.tool_calls]})
                    tool_results = []
                    for call in reply.tool_calls:
                        if call.name == "search_knowledge_base" and not business_intent:
                            result.tool_trace.append({"tool_name": call.name, "tool_use_id": call.id, "success": False, "error": "Knowledge retrieval is not eligible for this intent"})
                            tool_results.append({"type": "tool_result", "tool_use_id": call.id, "is_error": True, "content": "Knowledge retrieval is not eligible for this intent"})
                            continue
                        if call.name in self.tools._specs and not self.tools.retry_safe(call.name):
                            result.unsafe_attempted = True
                        try:
                            output = await self.tools.execute(role, call.name, call.arguments)
                            result.tools_used.append(call.name)
                            result.tool_trace.append({"tool_name": call.name, "tool_use_id": call.id, "success": True, "retry_safe": not result.unsafe_attempted})
                            tool_results.append({"type": "tool_result", "tool_use_id": call.id, "content": json.dumps(output)})
                        except Exception as exc:
                            result.tool_trace.append({"tool_name": call.name, "tool_use_id": call.id, "success": False, "error": str(exc)[:160]})
                            tool_results.append({"type": "tool_result", "tool_use_id": call.id, "is_error": True, "content": str(exc)[:160]})
                    messages.append({"role": "user", "content": tool_results})
                    continue
                if not reply.text.strip():
                    raise ValueError("Model returned an empty final response")
                result.text = reply.text.strip()
                result.status = "partial" if reply.truncated else "success"
                return result
            raise ValueError("Tool round limit reached without a final response")
        except Exception as exc:
            result.status = "failed"
            result.error = str(exc)[:160]
            return result
