# AgentFlow

AgentFlow is an English customer-support agent runtime with intent fusion, role routing, guarded tools, Redis conversation receipts, Chroma knowledge retrieval, Skills, MCP integration, monitoring, evaluation jobs, an interactive CLI, and a Vue operations console.

## Run the Python service

Use Python 3.12 or 3.13 and `uv`:

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e 'services/python[test]'
docker compose -f infra/compose.dev.yml up -d
cp .env.example .env
set -a
source .env
set +a
.venv/bin/uvicorn agentflow.api.app:app --port 8000
```

Set `AGENTFLOW_MODEL_API_KEY` and a compatible `AGENTFLOW_MODEL_NAME` before sending live chat requests. The development stack exposes Redis on port 6379 and Chroma on port 8001. `GET /health` checks required storage dependencies; `GET /openapi.json` publishes the API contract. Development permits unauthenticated requests. Production requires a JSON bearer token map in `AGENTFLOW_API_TOKENS`, for example `{"token-value":{"user_id":"user-1","role":"customer"}}`. Administrator tokens are required for knowledge writes and diagnostics.

## Run the web console

```sh
cd web
npm ci
npm run dev
```

Open `http://localhost:5173`. The console includes chat with request inspection, knowledge search/import/upload, Skills status/reload, fixed-suite evaluation, monitoring, and integration diagnostics. The API URL can be changed under Connections. Access tokens remain in browser memory and clear on reload; use an administrator token for operations pages in production. The development API allows the console origins listed in `AGENTFLOW_CORS_ORIGINS`.

## Complete Compose stack

Create `.env` from `.env.example` if you do not already have one, then set the model provider values in `.env`.

```sh
docker compose --env-file .env -p agentflow -f infra/compose.yml up -d --build
curl -fsS http://localhost:8080/api/health
```

The gateway serves the console at `http://localhost:8080` and the API under `/api`. Redis, Chroma, and Prometheus remain private to the Compose network. See [operations](docs/operations.md) for production tokens, startup behavior, backup and restore, and [release validation](docs/release-validation.md) for requirement evidence.

## CLI and verification

```sh
.venv/bin/agentflow chat --api-url http://localhost:8000
.venv/bin/python -B -m unittest discover -s tests -q
docker compose -f infra/compose.dev.yml config --quiet
cd web && npm ci && npm test && npm run build
bash scripts/verify_stack.sh
```

With the Compose services running, set `AGENTFLOW_LIVE_SERVICES=1` while running the Python test command to include the Redis and Chroma integration check.

Use `/new` to start a new CLI conversation and `/exit` to leave. Set `--token` when the API uses bearer authentication. The CLI sends requests to the same `/chat` workflow as other clients.

## Repository contents

- `services/python/agentflow/api/`: FastAPI contracts, authentication, and endpoint wiring.
- `services/python/agentflow/core/`: intent recognition, embedding, Skills loading, model client, state, and operations.
- `services/python/agentflow/agents/`: role orchestration and domain-specific tools.
- `services/python/agentflow/mcp/`: knowledge base, retrieval, guarded tool execution, and MCP client/server adapters.
- `services/python/agentflow/memory/`: Redis conversations and Chroma long-term memory.
- `services/python/agentflow/evaluation/`: intent, dialog, and retrieval evaluation.
- `infra/`: local services and the complete deployment stack.
- `web/`: English operations console and frontend state tests.
- `config/`: MCP server allowlist configuration.
- `data/knowledge/`: English demonstration knowledge.
- `skills/`: English business guidance for support roles.
- `docs/`: product requirements, technical design, and implementation status.
- `tests/`: unit, API, and repository checks.

Demonstration policies require replacement with approved content before production use. See [implementation status](docs/implementation-status.md) for coverage and remaining work.
