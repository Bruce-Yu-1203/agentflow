# AgentFlow

AgentFlow is an English customer-support agent runtime with intent fusion, role routing, guarded tools, Redis conversation receipts, Chroma knowledge retrieval, Skills, MCP integration, monitoring, evaluation jobs, and an interactive CLI. A Vue build shell is included; full console features and deployment packaging are planned for later stages.

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

## CLI and verification

```sh
.venv/bin/agentflow chat --api-url http://localhost:8000
.venv/bin/python -B -m unittest discover -s tests -q
docker compose -f infra/compose.dev.yml config --quiet
cd web && npm ci && npm test && npm run build
```

With the Compose services running, set `AGENTFLOW_LIVE_SERVICES=1` while running the Python test command to include the Redis and Chroma integration check.

Use `/new` to start a new CLI conversation and `/exit` to leave. Set `--token` when the API uses bearer authentication. The CLI sends requests to the same `/chat` workflow as other clients.

## Repository contents

- `services/python/`: FastAPI service, orchestration, persistence, retrieval, MCP, evaluation, monitoring, and CLI.
- `infra/`: local Redis and Chroma services.
- `config/`: MCP server allowlist configuration.
- `data/knowledge/`: English demonstration knowledge.
- `skills/`: English business guidance for support roles.
- `docs/`: product requirements, technical design, and implementation status.
- `tests/`: unit, API, and repository checks.

Demonstration policies require replacement with approved content before production use. See [implementation status](docs/implementation-status.md) for coverage and remaining work.
