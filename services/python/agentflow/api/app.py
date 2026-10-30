"""FastAPI application factory and initial API surface."""

import asyncio
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query, Response, UploadFile
import time
from uuid import uuid4
from redis.asyncio import Redis
from redis.exceptions import RedisError

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
from agentflow.api.auth import require_admin, resolve_identity
from agentflow.agents.orchestrator import Orchestrator
from agentflow.core.embedding import IntentEmbedding
from agentflow.core.intent import IntentRecognizer
from agentflow.core.model import AnthropicModelClient
from agentflow.core.memory import ConversationStore, LeaseLost, ReceiptConflict
from agentflow.core.knowledge import KnowledgeStore, parse_upload
from agentflow.core.skills import SkillManager
from agentflow.core.mcp import MCPManager
from agentflow.core.retrieval import RetrievalPipeline
from agentflow.core.mcp_server import build_mcp_server
from agentflow.core.operations import Operations
from agentflow.core.evaluation import EvaluationQueueFull, EvaluationService


def unavailable() -> None:
    raise HTTPException(status_code=501, detail="This capability is not implemented yet")


def create_app(settings: Settings | None = None, orchestrator: Orchestrator | None = None, store: ConversationStore | None = None, knowledge: KnowledgeStore | None = None, skills_manager: SkillManager | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.validate()
    app = FastAPI(title="AgentFlow API", version=__version__, description="English customer-support agent runtime")
    app.state.settings = settings
    if orchestrator is None and settings.model_api_key:
        model = AnthropicModelClient(settings.model_api_key, settings.model_base_url)
        embedding = IntentEmbedding(provider=settings.embedding_provider if settings.embedding_provider != "disabled" else "local", api_key=settings.embedding_api_key, endpoint=settings.embedding_base_url or "https://api.siliconflow.cn/v1/embeddings")
        recognizer = IntentRecognizer(model, settings.model_name, embedding=embedding, embedding_enabled=settings.embedding_provider != "disabled")
        orchestrator = Orchestrator(recognizer, model, settings.model_name)
    app.state.orchestrator = orchestrator
    app.state.operations = Operations()
    app.state.evaluation = EvaluationService(orchestrator.model if orchestrator else None, settings.model_name)
    if orchestrator is not None:
        orchestrator.operations = app.state.operations
    app.state.store = store or (ConversationStore(Redis.from_url(settings.redis_url, decode_responses=True)) if settings.environment == "production" else None)
    app.state.knowledge = knowledge
    app.state.skills = skills_manager
    app.state.mcp = None
    app.state.retrieval = None
    if orchestrator is not None and skills_manager is not None:
        orchestrator.skills = skills_manager
    if orchestrator is not None and knowledge is not None:
        orchestrator.tools.register_knowledge(knowledge)

    def get_knowledge() -> KnowledgeStore:
        if app.state.knowledge is None:
            import chromadb
            client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port) if settings.environment == "production" else chromadb.PersistentClient(path=settings.chroma_path)
            app.state.knowledge = KnowledgeStore(client)
            if app.state.orchestrator is not None:
                app.state.orchestrator.tools.register_knowledge(app.state.knowledge)
        return app.state.knowledge

    def get_skills() -> SkillManager:
        if app.state.skills is None:
            app.state.skills = SkillManager(settings.skills_dir)
            if app.state.orchestrator is not None:
                app.state.orchestrator.skills = app.state.skills
        return app.state.skills

    def get_mcp() -> MCPManager:
        if app.state.mcp is None:
            app.state.mcp = MCPManager(settings.mcp_config)
        return app.state.mcp

    def get_retrieval() -> RetrievalPipeline:
        if app.state.retrieval is None:
            app.state.retrieval = RetrievalPipeline(get_knowledge(), app.state.orchestrator.model if app.state.orchestrator else None, settings.model_name)
        return app.state.retrieval

    @app.get("/health", tags=["System"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.post("/chat", response_model=ChatResponse, tags=["Chat"])
    async def chat(body: ChatRequest, background_tasks: BackgroundTasks, authorization: str | None = Header(default=None)) -> ChatResponse:
        identity = resolve_identity(settings, authorization, body.user_id)
        if app.state.orchestrator is None:
            raise HTTPException(status_code=503, detail="Model service is not configured")
        started = time.monotonic()
        request_id = str(uuid4())
        client_request_id = body.client_request_id or str(uuid4())
        conv_id = body.conv_id or str(uuid4())
        if body.conv_id is None and body.client_request_id:
            from hashlib import sha256
            conv_id = sha256(f"{identity.user_id}:{client_request_id}".encode()).hexdigest()[:32]

        async def execute(history=None, previous_state=None) -> tuple[ChatResponse, object]:
            result = await app.state.orchestrator.run(body.message, history=history, previous_state=previous_state, request_id=request_id)
            response = ChatResponse(
            conv_id=conv_id, request_id=request_id, response=result.response,
            intent=result.intent.intent.value, intent_group=result.intent.intent_group,
            agent_type=result.route.primary, agent_types=[result.route.primary, *result.route.supporting],
            primary_agent=result.route.primary, supporting_agents=result.route.supporting,
            tools_used=result.tools_used, routing_reason=result.route.reason,
            routing_confidence=result.route.scores.get(result.route.primary, 0),
            escalated=result.escalated, latency_ms=(time.monotonic() - started) * 1000,
            entities=result.state["entities"], intent_confidence=result.intent.confidence,
            intent_source_scores=result.intent.source_scores,
            intent_embedding_source=result.intent.embedding_source, status=result.status,
            retryable=result.status == "failed", error_code="agent_failed" if result.status == "failed" else None,
            )
            app.state.operations.record(request_id, response.status, response.latency_ms, response.primary_agent, result.tool_trace)
            return response, result

        try:
            async with asyncio.timeout(50):
                if app.state.store is None:
                    response, _ = await execute()
                    return response
                async with await app.state.store.acquire(identity.user_id, conv_id, client_request_id) as lease:
                    previous = await app.state.store.receipt(identity.user_id, conv_id, client_request_id, body.message)
                    if previous and not previous["retryable"]:
                        return ChatResponse.model_validate(previous["response"])
                    context = await app.state.store.context(identity.user_id, conv_id, client_request_id)
                    response, result = await execute(context.history, context.state)
                    await app.state.store.commit(lease, identity.user_id, conv_id, client_request_id, body.message, response.model_dump(), context, result.state, result.tool_trace)
                    if response.status != "failed" and app.state.orchestrator.model is not None:
                        background_tasks.add_task(app.state.store.compress, identity.user_id, conv_id, client_request_id, app.state.orchestrator.model, settings.model_name)
                    return response
        except ReceiptConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except asyncio.TimeoutError as exc:
            raise HTTPException(status_code=504, detail="Chat request timed out") from exc
        except (LeaseLost, RedisError) as exc:
            raise HTTPException(status_code=503, detail="Conversation service is unavailable") from exc

    @app.post("/search", response_model=SearchResponse, tags=["Knowledge"])
    async def search(query: str = Query(min_length=1, max_length=2000), top_k: int = Query(default=5, ge=1, le=20), authorization: str | None = Header(default=None)) -> SearchResponse:
        require_admin(resolve_identity(settings, authorization))
        return SearchResponse(**(await get_retrieval().search(query, top_k)))

    @app.post("/knowledge/add", response_model=KnowledgeWriteResponse, tags=["Knowledge"])
    async def knowledge_add(body: DocumentBatch, authorization: str | None = Header(default=None)) -> KnowledgeWriteResponse:
        require_admin(resolve_identity(settings, authorization))
        return KnowledgeWriteResponse(**(await get_knowledge().add([item.model_dump(exclude_none=True) for item in body.documents])))

    @app.post("/knowledge/upload", response_model=KnowledgeWriteResponse, tags=["Knowledge"])
    async def knowledge_upload(file: UploadFile, authorization: str | None = Header(default=None)) -> KnowledgeWriteResponse:
        require_admin(resolve_identity(settings, authorization))
        try:
            documents = parse_upload(file.filename or "", await file.read(10 * 1024 * 1024 + 1))
            return KnowledgeWriteResponse(**(await get_knowledge().add(documents)))
        except (ValueError, KeyError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/knowledge/stats", response_model=KnowledgeStatsResponse, tags=["Knowledge"])
    async def knowledge_stats(authorization: str | None = Header(default=None)) -> KnowledgeStatsResponse:
        require_admin(resolve_identity(settings, authorization))
        return KnowledgeStatsResponse(total_chunks=await get_knowledge().count())

    @app.get("/skills", response_model=SkillsResponse, tags=["Skills"])
    async def skills(authorization: str | None = Header(default=None)) -> SkillsResponse:
        require_admin(resolve_identity(settings, authorization))
        return SkillsResponse(**get_skills().list())

    @app.post("/skills/reload", response_model=SkillsResponse, tags=["Skills"])
    async def skills_reload(authorization: str | None = Header(default=None)) -> SkillsResponse:
        require_admin(resolve_identity(settings, authorization))
        return SkillsResponse(**get_skills().reload())

    @app.get("/trace/tool/{request_id}", response_model=ToolTraceResponse, tags=["Operations"])
    async def trace_one(request_id: str, authorization: str | None = Header(default=None)) -> ToolTraceResponse:
        require_admin(resolve_identity(settings, authorization))
        trace = app.state.operations.one_trace(request_id)
        return ToolTraceResponse(request_id=request_id, found=trace is not None, trace=trace)

    @app.get("/trace/tools", response_model=RecentToolTracesResponse, tags=["Operations"])
    async def trace_recent(limit: int = Query(default=20, ge=1, le=200), authorization: str | None = Header(default=None)) -> RecentToolTracesResponse:
        require_admin(resolve_identity(settings, authorization))
        return RecentToolTracesResponse(traces=list(app.state.operations.traces)[:limit])

    @app.get("/monitor", tags=["Operations"])
    async def monitor(authorization: str | None = Header(default=None)) -> dict:
        require_admin(resolve_identity(settings, authorization))
        return app.state.operations.summary()

    @app.get("/metrics", tags=["Operations"])
    async def metrics(authorization: str | None = Header(default=None)) -> Response:
        require_admin(resolve_identity(settings, authorization))
        return Response(app.state.operations.metrics(), media_type="text/plain; version=0.0.4")

    @app.post("/eval/run", response_model=EvaluationJobResponse, status_code=202, tags=["Evaluation"])
    async def eval_run(body: EvaluationRequest | None = None, authorization: str | None = Header(default=None)) -> EvaluationJobResponse:
        require_admin(resolve_identity(settings, authorization))
        try:
            return EvaluationJobResponse(**app.state.evaluation.submit(body.model_dump(exclude_none=True) if body else {}))
        except EvaluationQueueFull as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/eval/jobs/{job_id}", response_model=EvaluationJobResponse, tags=["Evaluation"])
    async def eval_job(job_id: str, authorization: str | None = Header(default=None)) -> EvaluationJobResponse:
        require_admin(resolve_identity(settings, authorization))
        job = app.state.evaluation.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Evaluation job not found")
        return EvaluationJobResponse(**job)

    @app.get("/integrations/embedding", tags=["Integrations"])
    async def embedding_info() -> dict:
        unavailable()

    @app.post("/integrations/embedding/check", tags=["Integrations"])
    async def embedding_check(body: dict) -> dict:
        unavailable()

    @app.get("/integrations/mcp", tags=["Integrations"])
    async def mcp_info(authorization: str | None = Header(default=None)) -> dict:
        require_admin(resolve_identity(settings, authorization))
        return get_mcp().info()

    @app.post("/integrations/mcp/call", tags=["Integrations"])
    async def mcp_call(body: MCPCallRequest, authorization: str | None = Header(default=None)) -> dict:
        require_admin(resolve_identity(settings, authorization))
        try:
            return await get_mcp().call("admin", body.tool_name, body.arguments)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    app.mount("/mcp", build_mcp_server(get_knowledge).streamable_http_app())
    return app


app = create_app()
