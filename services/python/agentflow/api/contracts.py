"""Public request and response contracts."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    user_id: str = Field(default="anonymous", min_length=1, max_length=256)
    conv_id: str | None = Field(default=None, min_length=1, max_length=256)
    client_request_id: str | None = Field(default=None, min_length=1, max_length=128)


class ChatResponse(BaseModel):
    conv_id: str
    request_id: str
    response: str
    intent: str = "other"
    intent_group: str = "other"
    agent_type: str = "general"
    agent_types: list[str] = Field(default_factory=list)
    primary_agent: str = "general"
    supporting_agents: list[str] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    routing_reason: str = ""
    routing_confidence: float = 0.0
    escalated: bool = False
    latency_ms: float = 0.0
    knowledge_used: bool = False
    entities: dict[str, list[str]] = Field(default_factory=dict)
    intent_confidence: float = 0.0
    intent_source_scores: dict[str, Any] = Field(default_factory=dict)
    intent_embedding_source: str = ""
    status: Literal["success", "partial", "failed"] = "success"
    retryable: bool = False
    error_code: str | None = None
    performance: dict[str, Any] = Field(default_factory=dict)


class DocumentInput(BaseModel):
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    document_id: str | None = Field(default=None, min_length=1)


class DocumentBatch(BaseModel):
    documents: list[DocumentInput] = Field(min_length=1)


class KnowledgeWriteResponse(BaseModel):
    added_chunks: int
    total_chunks: int


class KnowledgeStatsResponse(BaseModel):
    total_chunks: int


class SearchHit(BaseModel):
    title: str
    content: str
    score: float
    chunk: int
    document_id: str
    version: str


class SearchResponse(BaseModel):
    query: str
    results: list[SearchHit]
    reranked: bool = False
    cached: bool = False


class SkillInfo(BaseModel):
    name: str
    description: str = ""
    path: str
    keywords: list[str] = Field(default_factory=list)
    agents: list[str] = Field(default_factory=list)
    enabled: bool = True
    content_chars: int = 0


class SkillsResponse(BaseModel):
    count: int
    skills: list[SkillInfo]
    errors: list[str] = Field(default_factory=list)


class IntentCase(BaseModel):
    message: str = Field(min_length=1)
    expected_intent: str
    context: dict[str, Any] | None = None


class DialogCase(BaseModel):
    question: str | None = None
    turns: list[str] | None = Field(default=None, max_length=50)
    reference_answer: str | None = None
    evidence: str | None = None
    expected_agent: Literal["general", "technical", "billing", "escalation"] | None = None
    expected_intent: str | None = None
    required_tools: list[str] = Field(default_factory=list, max_length=20)
    expected_entities: dict[str, list[str]] = Field(default_factory=dict)


class EvaluationRequest(BaseModel):
    intent_cases: list[IntentCase] | None = Field(default=None, max_length=200)
    dialog_cases: list[DialogCase] | None = Field(default=None, max_length=100)


class EvaluationJobResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    completed: int = 0
    total: int = 0
    result: dict[str, Any] | None = None
    error: str | None = None


class ToolTraceResponse(BaseModel):
    request_id: str
    found: bool
    trace: dict[str, Any] | None = None


class RecentToolTracesResponse(BaseModel):
    traces: list[dict[str, Any]]


class MCPCallRequest(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
