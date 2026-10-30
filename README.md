# AgentFlow

AgentFlow is an English customer-support agent runtime. The Python service is being built in stages; the Vue console is planned for a later stage. The repository currently includes API contracts, development service configuration, example knowledge, and role Skills.

## Start the Stage 1 API shell

Use Python 3.12 or 3.13 and `uv`:

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e 'services/python[test]'
docker compose -f infra/compose.dev.yml up -d
.venv/bin/uvicorn agentflow.api.app:app --reload --port 8000
```

The API health check is `GET http://localhost:8000/health`; its OpenAPI schema is at `GET http://localhost:8000/openapi.json`. Redis uses port 6379 and the development Chroma service uses host port 8001. Copy `.env.example` to `.env` and load it into your shell when configuring model access. Future stages will activate the placeholder endpoints, which currently return HTTP 501.

## Repository contents

- `services/python/`: Python package and API contracts.
- `infra/`: development service configuration.
- `data/knowledge/`: English demonstration knowledge documents.
- `skills/`: English business rules for General, Technical, and Billing roles.
- `docs/`: requirements, design, and implementation matrix.
- `tests/`: repository and stage verification.

Demonstration policies must be replaced with approved content before production use.
