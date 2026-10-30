"""FastAPI application factory and initial API surface."""

from fastapi import FastAPI, HTTPException, Query, UploadFile

from agentflow import __version__
from agentflow.api.contracts import (
    ChatRequest,
    ChatResponse,
    DocumentBatch,
    EvaluationJobResponse,
    EvaluationRequest,
    KnowledgeStatsResponse,
    KnowledgeWriteResponse,
    MCPCallRequest,
    RecentToolTracesResponse,
    SearchResponse,
    SkillsResponse,
    ToolTraceResponse,
)
from agentflow.config import Settings


def unavailable() -> None:
    raise HTTPException(status_code=501, detail="This capability is not implemented yet")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.validate()
    app = FastAPI(title="AgentFlow API", version=__version__, description="English customer-support agent runtime")
    app.state.settings = settings

    @app.get("/health", tags=["System"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.post("/chat", response_model=ChatResponse, tags=["Chat"])
    async def chat(body: ChatRequest) -> ChatResponse:
        unavailable()

    @app.post("/search", response_model=SearchResponse, tags=["Knowledge"])
    async def search(query: str = Query(min_length=1, max_length=2000), top_k: int = Query(default=5, ge=1, le=20)) -> SearchResponse:
        unavailable()

    @app.post("/knowledge/add", response_model=KnowledgeWriteResponse, tags=["Knowledge"])
    async def knowledge_add(body: DocumentBatch) -> KnowledgeWriteResponse:
        unavailable()

    @app.post("/knowledge/upload", response_model=KnowledgeWriteResponse, tags=["Knowledge"])
    async def knowledge_upload(file: UploadFile) -> KnowledgeWriteResponse:
        unavailable()

    @app.get("/knowledge/stats", response_model=KnowledgeStatsResponse, tags=["Knowledge"])
    async def knowledge_stats() -> KnowledgeStatsResponse:
        unavailable()

    @app.get("/skills", response_model=SkillsResponse, tags=["Skills"])
    async def skills() -> SkillsResponse:
        unavailable()

    @app.post("/skills/reload", response_model=SkillsResponse, tags=["Skills"])
    async def skills_reload() -> SkillsResponse:
        unavailable()

    @app.get("/trace/tool/{request_id}", response_model=ToolTraceResponse, tags=["Operations"])
    async def trace_one(request_id: str) -> ToolTraceResponse:
        unavailable()

    @app.get("/trace/tools", response_model=RecentToolTracesResponse, tags=["Operations"])
    async def trace_recent(limit: int = Query(default=20, ge=1, le=200)) -> RecentToolTracesResponse:
        unavailable()

    @app.get("/monitor", tags=["Operations"])
    async def monitor() -> dict:
        unavailable()

    @app.get("/metrics", tags=["Operations"])
    async def metrics() -> str:
        unavailable()

    @app.post("/eval/run", response_model=EvaluationJobResponse, status_code=202, tags=["Evaluation"])
    async def eval_run(body: EvaluationRequest | None = None) -> EvaluationJobResponse:
        unavailable()

    @app.get("/eval/jobs/{job_id}", response_model=EvaluationJobResponse, tags=["Evaluation"])
    async def eval_job(job_id: str) -> EvaluationJobResponse:
        unavailable()

    @app.get("/integrations/embedding", tags=["Integrations"])
    async def embedding_info() -> dict:
        unavailable()

    @app.post("/integrations/embedding/check", tags=["Integrations"])
    async def embedding_check(body: dict) -> dict:
        unavailable()

    @app.get("/integrations/mcp", tags=["Integrations"])
    async def mcp_info() -> dict:
        unavailable()

    @app.post("/integrations/mcp/call", tags=["Integrations"])
    async def mcp_call(body: MCPCallRequest) -> dict:
        unavailable()

    return app


app = create_app()
