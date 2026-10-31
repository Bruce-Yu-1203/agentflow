"""Fine-grained customer intent recognition and signal fusion."""

import asyncio
from dataclasses import dataclass, field
from enum import StrEnum
import hashlib
import json
import math
import re
import time
from typing import Any

from agentflow.core.embedding import IntentEmbedding, cosine
from agentflow.core.model import ModelClient
from agentflow.core.state import extract_entities


class IntentCategory(StrEnum):
    QUERY = "query"
    COMPLAINT = "complaint"
    REQUEST = "request"
    GREETING = "greeting"
    ESCALATION = "escalation"
    TECHNICAL = "technical"
    BILLING = "billing"
    ACCOUNT = "account"
    FEEDBACK = "feedback"
    ORDER_STATUS = "order_status"
    LOGISTICS = "logistics"
    REFUND = "refund"
    INVOICE = "invoice"
    PAYMENT_ISSUE = "payment_issue"
    ACCOUNT_SECURITY = "account_security"
    TECHNICAL_LOGIN = "technical_login"
    TECHNICAL_CRASH = "technical_crash"
    HUMAN_HANDOFF = "human_handoff"
    OTHER = "other"


class UrgencyLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


INTENT_GROUPS = {
    IntentCategory.ORDER_STATUS: IntentCategory.QUERY,
    IntentCategory.LOGISTICS: IntentCategory.QUERY,
    IntentCategory.REFUND: IntentCategory.BILLING,
    IntentCategory.INVOICE: IntentCategory.BILLING,
    IntentCategory.PAYMENT_ISSUE: IntentCategory.BILLING,
    IntentCategory.ACCOUNT_SECURITY: IntentCategory.ACCOUNT,
    IntentCategory.TECHNICAL_LOGIN: IntentCategory.TECHNICAL,
    IntentCategory.TECHNICAL_CRASH: IntentCategory.TECHNICAL,
    IntentCategory.HUMAN_HANDOFF: IntentCategory.ESCALATION,
}
SPECIFIC = set(INTENT_GROUPS)
GENERIC = {IntentCategory.QUERY, IntentCategory.BILLING, IntentCategory.ACCOUNT, IntentCategory.TECHNICAL, IntentCategory.ESCALATION}

TEMPLATES: dict[IntentCategory, list[str]] = {
    IntentCategory.QUERY: ["Can you answer a question about my account?", "Where can I find the policy?", "How does this service work?"],
    IntentCategory.COMPLAINT: ["I have waited for hours and nobody helped", "Your service is disappointing", "I want to complain about the support experience"],
    IntentCategory.REQUEST: ["Please help me change a setting", "Can you update my details?", "I need help with an action"],
    IntentCategory.GREETING: ["Hello", "Hi, is anyone there?", "Good morning"],
    IntentCategory.ESCALATION: ["Please escalate this issue", "I need a supervisor", "This needs urgent review"],
    IntentCategory.TECHNICAL: ["The application has an error", "The service is not working", "I need technical help"],
    IntentCategory.BILLING: ["I have a billing question", "There is a charge on my account", "I need payment help"],
    IntentCategory.ACCOUNT: ["I want to change my email", "How do I close my account?", "Please update my profile"],
    IntentCategory.FEEDBACK: ["The service was excellent", "Thank you, that helped", "I am satisfied with the support"],
    IntentCategory.ORDER_STATUS: ["What is my order status?", "Has my order shipped?", "Where is order AB1234?"],
    IntentCategory.LOGISTICS: ["When will my delivery arrive?", "The tracking has not updated", "How long does shipping take?"],
    IntentCategory.REFUND: ["I want a refund", "How do I return this item?", "When will the refund arrive?"],
    IntentCategory.INVOICE: ["Please send my invoice", "How can I change the invoice name?", "Where is my electronic invoice?"],
    IntentCategory.PAYMENT_ISSUE: ["I was charged twice", "My payment failed", "There is an unexpected payment"],
    IntentCategory.ACCOUNT_SECURITY: ["My account may be compromised", "I saw a suspicious sign-in", "How do I reset my password?"],
    IntentCategory.TECHNICAL_LOGIN: ["Sign-in returns 401", "I cannot log in", "The verification code never arrives"],
    IntentCategory.TECHNICAL_CRASH: ["The app keeps crashing", "The page returns 500", "The system exits unexpectedly"],
    IntentCategory.HUMAN_HANDOFF: ["I want a human agent", "Connect me to a person", "Please transfer me to support"],
}

SPECIFIC_PATTERNS: dict[IntentCategory, tuple[str, ...]] = {
    IntentCategory.HUMAN_HANDOFF: ("human agent", "real person", "talk to a person", "live agent"),
    IntentCategory.ORDER_STATUS: ("order status", "has my order shipped", "where is my order"),
    IntentCategory.LOGISTICS: ("delivery", "shipping", "tracking", "parcel", "courier"),
    IntentCategory.REFUND: ("refund", "return this", "return an item", "money back"),
    IntentCategory.INVOICE: ("invoice", "tax number", "receipt"),
    IntentCategory.PAYMENT_ISSUE: ("charged twice", "double charge", "payment failed", "unexpected charge", "overcharged"),
    IntentCategory.ACCOUNT_SECURITY: ("compromised account", "suspicious sign-in", "reset my password", "two-factor"),
    IntentCategory.TECHNICAL_LOGIN: ("cannot log in", "can't log in", "sign-in failed", "login failed", "401", "verification code"),
    IntentCategory.TECHNICAL_CRASH: ("crash", "500", "server error", "app error"),
}
GENERIC_PATTERNS: dict[IntentCategory, tuple[str, ...]] = {
    IntentCategory.ESCALATION: ("escalate", "supervisor", "manager"),
    IntentCategory.COMPLAINT: ("terrible", "disappointed", "horrible", "too long"),
    IntentCategory.QUERY: ("?", "how", "what", "status"),
    IntentCategory.REQUEST: ("please", "help me", "I need"),
    IntentCategory.GREETING: ("hello", "hi", "good morning"),
    IntentCategory.BILLING: ("charge", "billing", "payment"),
    IntentCategory.TECHNICAL: ("error", "failed", "timeout"),
    IntentCategory.ACCOUNT: ("account", "email", "password"),
}


@dataclass
class IntentResult:
    intent: IntentCategory
    confidence: float
    urgency: UrgencyLevel
    intent_group: str
    entities: dict[str, list[str]]
    reasoning: str = ""
    latency_ms: float = 0.0
    source_scores: dict[str, float] = field(default_factory=dict)
    embedding_source: str = "local-ngram"


def intent_group(intent: IntentCategory) -> str:
    return INTENT_GROUPS.get(intent, intent).value


def _match_phrase(message: str, phrase: str) -> bool:
    if phrase == "?":
        return "?" in message
    return bool(re.search(r"(?<![a-z])" + re.escape(phrase.lower()) + r"(?![a-z])", message))


class IntentRecognizer:
    def __init__(
        self,
        model_client: ModelClient | None,
        model_name: str,
        *,
        embedding: IntentEmbedding | None = None,
        embedding_enabled: bool = True,
        threshold: float = 0.5,
    ):
        self.model_client = model_client
        self.model_name = model_name
        self.embedding = embedding or IntentEmbedding(provider="local")
        self.embedding_enabled = embedding_enabled
        self.threshold = threshold
        self.templates = {category: list(values) for category, values in TEMPLATES.items()}
        self._cache: dict[str, tuple[float, IntentResult]] = {}
        self.cache_hits = 0
        self.cache_misses = 0

    async def recognize(self, message: str, history: list[dict[str, str]] | None = None) -> IntentResult:
        cleaned = message.encode("utf-8", errors="ignore").decode("utf-8").strip()
        short_history = [{"role": str(item.get("role", "user"))[:20], "content": str(item.get("content", ""))} for item in (history or [])[-3:]]
        key = hashlib.sha256(json.dumps([cleaned, short_history, self.model_name, self.embedding_enabled], sort_keys=True).encode()).hexdigest()
        hit = self._cache.get(key)
        if hit and time.monotonic() < hit[0]:
            self.cache_hits += 1
            return hit[1]
        self.cache_misses += 1
        started = time.monotonic()
        model_task = asyncio.create_task(self._from_model(cleaned, short_history))
        vector_task = asyncio.create_task(self._from_vectors(cleaned)) if self.embedding_enabled else None
        pattern = self._from_patterns(cleaned)
        model_signal = await model_task
        vector_signal = await vector_task if vector_task else {"intent": IntentCategory.OTHER, "confidence": 0.0, "source": "disabled"}
        chosen, confidence, scores = self._vote(model_signal, vector_signal, pattern)
        result = IntentResult(
            intent=chosen,
            confidence=confidence,
            urgency=self._urgency(cleaned, chosen),
            intent_group=intent_group(chosen),
            entities=extract_entities(cleaned),
            reasoning=str(model_signal.get("reasoning", ""))[:240],
            latency_ms=(time.monotonic() - started) * 1000,
            source_scores=scores,
            embedding_source=str(vector_signal.get("source", "unavailable")),
        )
        if len(self._cache) >= 1000:
            for old_key in list(self._cache)[:500]:
                self._cache.pop(old_key, None)
        ttl = 60 if result.embedding_source == "local-ngram" and self.embedding.online_configured else 300
        self._cache[key] = (time.monotonic() + ttl, result)
        return result

    async def _from_model(self, message: str, history: list[dict[str, str]]) -> dict[str, Any]:
        if self.model_client is None:
            return {"intent": IntentCategory.OTHER, "confidence": 0.0, "failed": True}
        examples = "\n".join(f'"{examples[0]}" => {category.value}' for category, examples in self.templates.items())
        context = "\n".join(f"{item['role']}: {item['content']}" for item in history)
        prompt = (
            "Classify the customer message. Prefer a specific intent over its broad parent. "
            "Return only JSON with intent, confidence from 0 to 1, and a short reasoning string.\n"
            f"Allowed intents: {', '.join(category.value for category in IntentCategory)}\n"
            f"Examples:\n{examples}\nRecent conversation:\n{context}\nCustomer message:\n{message}"
        )
        try:
            reply = await self.model_client.complete(
                stage="intent", model=self.model_name, system="You classify customer support intent.",
                messages=[{"role": "user", "content": prompt}], max_tokens=256, temperature=0.1, timeout=8,
            )
            if reply.truncated:
                raise ValueError("Truncated intent response")
            start, end = reply.text.find("{"), reply.text.rfind("}") + 1
            data = json.loads(reply.text[start:end])
            category = IntentCategory(data["intent"])
            confidence = data["confidence"]
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise ValueError("Invalid intent confidence")
            return {"intent": category, "confidence": float(confidence), "reasoning": str(data.get("reasoning", ""))}
        except asyncio.CancelledError:
            raise
        except Exception:
            return {"intent": IntentCategory.OTHER, "confidence": 0.0, "failed": True}

    async def _from_vectors(self, message: str) -> dict[str, Any]:
        try:
            groups, query, source = await self.embedding.vectors(message, {category.value: values for category, values in self.templates.items()})
            ranked = [(max(cosine(query, vector) for vector in values), IntentCategory(name)) for name, values in groups.items() if values]
            confidence, category = max(ranked, default=(0.0, IntentCategory.OTHER))
            return {"intent": category, "confidence": min(1.0, max(0.0, confidence)), "source": source}
        except asyncio.CancelledError:
            raise
        except Exception:
            return {"intent": IntentCategory.OTHER, "confidence": 0.0, "source": "unavailable"}

    @staticmethod
    def _from_patterns(message: str) -> dict[str, Any]:
        lowered = message.lower()
        for patterns in (SPECIFIC_PATTERNS, GENERIC_PATTERNS):
            best = (0.0, IntentCategory.OTHER)
            for category, phrases in patterns.items():
                hits = sum(_match_phrase(lowered, phrase) for phrase in phrases)
                score = min(1.0, 0.5 + 0.25 * (hits - 1)) if hits else 0.0
                if score > best[0]:
                    best = (score, category)
            if best[0]:
                return {"intent": best[1], "confidence": best[0]}
        return {"intent": IntentCategory.OTHER, "confidence": 0.0}

    def _vote(self, model: dict[str, Any], vector: dict[str, Any], pattern: dict[str, Any]) -> tuple[IntentCategory, float, dict[str, float]]:
        signals = (model, vector, pattern)
        scores = {name: float(signal.get("confidence", 0) or 0) for name, signal in zip(("llm", "embedding", "pattern"), signals)}
        if model.get("failed"):
            for signal in (vector, pattern):
                if signal["intent"] != IntentCategory.OTHER and signal["confidence"] > 0:
                    return signal["intent"], float(signal["confidence"]), scores
            return IntentCategory.OTHER, 0.0, scores
        weighted = ((model, 0.7), (vector, 0.2), (pattern, 0.1)) if self.embedding_enabled else ((model, 0.85), (pattern, 0.15))
        categories: dict[IntentCategory, float] = {}
        groups: dict[str, float] = {}
        for signal, weight in weighted:
            category = signal["intent"]
            value = float(signal["confidence"]) * weight
            categories[category] = categories.get(category, 0.0) + value
            group = intent_group(category)
            groups[group] = groups.get(group, 0.0) + value
        group = max(groups, key=groups.get)
        group_score = groups[group]
        winner = max((category for category in categories if intent_group(category) == group), key=categories.get)
        if group_score < self.threshold:
            return IntentCategory.OTHER, group_score, scores
        if (winner in GENERIC and pattern["intent"] in SPECIFIC and intent_group(pattern["intent"]) == group
                and pattern["confidence"] >= 0.5 and group_score < 0.8):
            scores["refined_by_pattern"] = pattern["confidence"]
            return pattern["intent"], max(group_score, pattern["confidence"]), scores
        return winner, group_score, scores

    @staticmethod
    def _urgency(message: str, intent: IntentCategory) -> UrgencyLevel:
        lowered = message.lower()
        lowered = re.sub(r"\b(?:not|no|isn't|is not)\s+(?:an?\s+)?(?:emergency|urgent|asap|now)\b", "", lowered)
        if any(_match_phrase(lowered, term) for term in ("emergency", "critical", "immediately", "asap")):
            return UrgencyLevel.CRITICAL
        if any(_match_phrase(lowered, term) for term in ("urgent", "today", "right now", "as soon as possible")):
            return UrgencyLevel.HIGH
        if intent in {IntentCategory.ESCALATION, IntentCategory.HUMAN_HANDOFF}:
            return UrgencyLevel.HIGH
        if intent == IntentCategory.COMPLAINT or _match_phrase(lowered, "soon"):
            return UrgencyLevel.MEDIUM
        return UrgencyLevel.LOW

    async def check_embedding(self, message: str) -> dict[str, Any]:
        if not self.embedding_enabled:
            return {"success": False, "source": "disabled", "error": "embedding_branch_disabled"}
        started = time.monotonic()
        signal = await self._from_vectors(message)
        return {
            "success": signal["source"].startswith("online/"),
            "source": signal["source"],
            "intent": signal["intent"].value,
            "confidence": signal["confidence"],
            "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
            "status": self.embedding.status(),
        }
