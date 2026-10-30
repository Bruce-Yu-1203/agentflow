"""Deterministic advisory tools with role and schema enforcement."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import inspect
from typing import Any, Callable

from jsonschema import Draft202012Validator


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    properties: dict[str, Any]
    required: tuple[str, ...]
    roles: frozenset[str]
    handler: Callable[..., dict[str, Any]]
    retry_safe: bool = True

    @property
    def schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": self.properties, "required": list(self.required), "additionalProperties": False}

    def model_definition(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "input_schema": self.schema}


def inspect_request_context(message: str, entities: dict[str, list[str]]) -> dict[str, Any]:
    return {"message_excerpt": message[:300], "available_fields": sorted(key for key, values in entities.items() if values)}


def suggest_required_fields(topic: str) -> dict[str, Any]:
    fields = {"order": ["order ID"], "refund": ["order ID", "purchase date"], "invoice": ["order ID", "billing name"], "technical": ["error code", "device and browser"]}
    return {"topic": topic, "recommended_fields": fields.get(topic.lower(), ["relevant reference number"])}


def lookup_error_code(code: str) -> dict[str, Any]:
    descriptions = {"401": "Authentication failed or the session expired", "403": "Access was denied", "404": "The requested resource was not found", "500": "A server error occurred", "503": "The service is temporarily unavailable"}
    return {"code": code, "description": descriptions.get(code, "Unknown error code; ask for the full message and context"), "verified_system_status": False}


def build_diagnostic_plan(problem: str) -> dict[str, Any]:
    return {"problem": problem[:300], "steps": ["Record the exact error and time", "Retry once and note whether the issue persists", "Check the service status and relevant account permissions", "Share sanitized logs with support if the issue continues"]}


def check_billing_fields(entities: dict[str, list[str]], issue: str) -> dict[str, Any]:
    required = ["order_id"] if issue in {"refund", "invoice"} else ["amount"]
    missing = [field for field in required if not entities.get(field)]
    return {"issue": issue, "missing_fields": missing, "verified_payment": False, "eligible_for_refund": None}


def compare_amounts(expected: str, actual: str) -> dict[str, Any]:
    try:
        expected_value, actual_value = Decimal(expected), Decimal(actual)
    except InvalidOperation as exc:
        raise ValueError("Amounts must be decimal numbers") from exc
    if not expected_value.is_finite() or not actual_value.is_finite():
        raise ValueError("Amounts must be finite")
    return {"expected": str(expected_value), "actual": str(actual_value), "difference": str(actual_value - expected_value), "verified_charge": False}


def create_handoff_summary(message: str, entities: dict[str, list[str]]) -> dict[str, Any]:
    return {"summary": message[:500], "known_fields": {key: value for key, value in entities.items() if value}, "ticket_created": False}


STRING = {"type": "string", "minLength": 1, "maxLength": 2000}
ENTITIES = {"type": "object", "additionalProperties": {"type": "array", "items": {"type": "string"}, "maxItems": 10}}
TOOL_SPECS = [
    ToolSpec("inspect_request_context", "List fields supplied by the customer.", {"message": STRING, "entities": ENTITIES}, ("message", "entities"), frozenset({"general"}), inspect_request_context),
    ToolSpec("suggest_required_fields", "Suggest fields needed to investigate a topic.", {"topic": STRING}, ("topic",), frozenset({"general"}), suggest_required_fields),
    ToolSpec("lookup_error_code", "Explain a common HTTP error code without claiming live system access.", {"code": STRING}, ("code",), frozenset({"technical"}), lookup_error_code),
    ToolSpec("build_diagnostic_plan", "Provide safe diagnostic steps.", {"problem": STRING}, ("problem",), frozenset({"technical"}), build_diagnostic_plan),
    ToolSpec("check_billing_fields", "List missing billing fields; no payment verification.", {"entities": ENTITIES, "issue": STRING}, ("entities", "issue"), frozenset({"billing"}), check_billing_fields),
    ToolSpec("compare_amounts", "Calculate a difference between user-provided amounts.", {"expected": STRING, "actual": STRING}, ("expected", "actual"), frozenset({"billing"}), compare_amounts),
    ToolSpec("create_handoff_summary", "Prepare a summary without creating a support ticket.", {"message": STRING, "entities": ENTITIES}, ("message", "entities"), frozenset({"escalation"}), create_handoff_summary),
]


class ToolRegistry:
    def __init__(self, specs: list[ToolSpec] | None = None):
        self._specs = {spec.name: spec for spec in (specs or TOOL_SPECS)}

    def definitions(self, role: str) -> list[dict[str, Any]]:
        return [spec.model_definition() for spec in self._specs.values() if role in spec.roles]

    def register_knowledge(self, knowledge: Any) -> None:
        async def search_knowledge_base(query: str, top_k: int = 5) -> dict[str, Any]:
            return {"results": await knowledge.search(query, top_k)}
        self._specs["search_knowledge_base"] = ToolSpec(
            "search_knowledge_base", "Retrieve approved knowledge passages with provenance.",
            {"query": STRING, "top_k": {"type": "integer", "minimum": 1, "maximum": 20}}, ("query",),
            frozenset({"general", "technical", "billing"}), search_knowledge_base,
        )

    def retry_safe(self, name: str) -> bool:
        return self._specs[name].retry_safe

    async def execute(self, role: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        spec = self._specs.get(name)
        if spec is None or role not in spec.roles:
            raise PermissionError(f"Tool {name} is not permitted for {role}")
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be an object")
        errors = list(Draft202012Validator(spec.schema).iter_errors(arguments))
        if errors:
            raise ValueError(f"Invalid tool arguments: {errors[0].message}")
        output = spec.handler(**arguments)
        return await output if inspect.isawaitable(output) else output
