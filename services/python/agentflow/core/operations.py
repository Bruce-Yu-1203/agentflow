"""Redacted traces, Prometheus metrics, and specialist health."""

from collections import defaultdict, deque
import re
import time
from typing import Any

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest


SECRET_PATTERN = re.compile(r"(?i)(bearer\s+\S+|(?:api[_-]?key|password|token)\s*[:=]\s*\S+|\b\d{13,19}\b)")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if re.search(r"(?i)(password|secret|token|authorization|api_key)", key) else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return SECRET_PATTERN.sub("[REDACTED]", value)[:1000]
    return value


class Operations:
    def __init__(self):
        self.registry = CollectorRegistry()
        self.chat_total = Counter("agentflow_chat_total", "Chat responses by status", ["status"], registry=self.registry)
        self.chat_latency = Histogram("agentflow_chat_latency_seconds", "Chat request duration", registry=self.registry)
        self.tool_total = Counter("agentflow_tool_total", "Tool calls by result", ["tool", "success"], registry=self.registry)
        self.traces: deque[dict[str, Any]] = deque(maxlen=200)
        self.agent_samples: dict[str, deque[tuple[bool, float]]] = defaultdict(lambda: deque(maxlen=20))
        self.cooldown_until: dict[str, float] = {}
        self.recovery_probe: set[str] = set()

    def record(self, request_id: str, status: str, latency_ms: float, primary: str, trace: list[dict[str, Any]]) -> None:
        self.chat_total.labels(status=status).inc()
        self.chat_latency.observe(latency_ms / 1000)
        for item in trace:
            self.tool_total.labels(tool=str(item.get("tool_name", "unknown")), success=str(bool(item.get("success", False))).lower()).inc()
        self.traces.appendleft(redact({"request_id": request_id, "status": status, "primary_agent": primary, "latency_ms": round(latency_ms, 1), "tools": trace}))
        if primary in {"technical", "billing"}:
            samples = self.agent_samples[primary]
            samples.append((status == "success", latency_ms))
            if len(samples) >= 5:
                success_rate = sum(ok for ok, _ in samples) / len(samples)
                average_ms = sum(ms for _, ms in samples) / len(samples)
                penalty = max(1 - success_rate, min(1, average_ms / 10000))
                if penalty >= 0.5:
                    self.cooldown_until[primary] = time.monotonic() + 60
                    self.recovery_probe.discard(primary)
                elif status == "success":
                    self.cooldown_until.pop(primary, None)
                    self.recovery_probe.discard(primary)

    def unavailable_roles(self) -> set[str]:
        now = time.monotonic()
        result = set()
        for role, until in self.cooldown_until.items():
            if now < until or role in self.recovery_probe:
                result.add(role)
            else:
                self.recovery_probe.add(role)
        return result

    def one_trace(self, request_id: str) -> dict[str, Any] | None:
        return next((item for item in self.traces if item["request_id"] == request_id), None)

    def summary(self) -> dict[str, Any]:
        return {"recent_requests": len(self.traces), "agents": {role: {"samples": len(samples), "success_rate": round(sum(ok for ok, _ in samples) / len(samples), 3) if samples else None, "cooldown_seconds": round(max(0, self.cooldown_until.get(role, 0) - time.monotonic()), 1)} for role, samples in self.agent_samples.items()}}

    def metrics(self) -> str:
        return generate_latest(self.registry).decode()
