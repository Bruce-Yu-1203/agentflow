"""Extract and merge business fields across conversation turns."""

import re
from typing import Any


ENTITY_KEYS = ("order_id", "product", "date", "amount", "error_code")


def extract_entities(message: str) -> dict[str, list[str]]:
    patterns = {
        "order_id": r"(?:\border\s+(?:number|id)\s*[:#-]?\s*|\border\s*[:#-]\s*|#)([A-Za-z0-9_-]{4,32})\b",
        "date": r"\b(?:today|tomorrow|yesterday|this week|next week|\d{4}[-/.]\d{1,2}[-/.]\d{1,2})\b",
        "amount": r"(?:[$€£]\s*\d+(?:\.\d{1,2})?|\b\d+(?:\.\d{1,2})?\s*(?:USD|CNY|EUR|GBP)\b)",
        "error_code": r"\b[45]\d{2}\b",
    }
    result = {key: [] for key in ENTITY_KEYS}
    for key, pattern in patterns.items():
        result[key] = list(dict.fromkeys(value.strip() for value in re.findall(pattern, message, flags=re.I)))
    return result


def merge_state(
    previous: dict[str, Any] | None,
    entities: dict[str, list[str]],
    intent_group: str,
    message: str,
    request_id: str,
) -> dict[str, Any]:
    previous = previous if isinstance(previous, dict) else {}
    old_entities = previous.get("entities", {})
    old_entities = old_entities if isinstance(old_entities, dict) else {}
    old_sources = previous.get("sources", {})
    old_sources = old_sources if isinstance(old_sources, dict) else {}
    domain = "commerce" if intent_group in {"billing", "query"} else intent_group
    neutral = domain in {"greeting", "feedback", "other", "complaint", "request", "escalation"}
    new_task = bool(re.search(r"\b(?:new|another|different)\s+(?:question|task|order)\b|\bswitch(?:ing)?\s+(?:orders|topics)\b", message, re.I))
    changed_order = bool(entities.get("order_id") and old_entities.get("order_id") and entities["order_id"] != old_entities["order_id"])
    if neutral:
        domain = previous.get("domain", "commerce" if entities.get("order_id") else "general") if not new_task else "general"
    retain = not (changed_order or new_task) and (neutral or domain == previous.get("domain"))
    merged = {key: list(value) for key, value in old_entities.items() if isinstance(value, list)} if retain else {}
    sources = dict(old_sources) if retain else {}
    for key in ENTITY_KEYS:
        values = list(entities.get(key, []))
        if values:
            merged[key] = values
            sources[key] = request_id
        else:
            merged.setdefault(key, [])
    return {"domain": domain, "entities": merged, "sources": sources}
