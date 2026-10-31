# AgentFlow Operations

## Startup

The complete local stack needs Docker Compose. From a clean checkout, run:

```sh
cp .env.example .env
```

Set `AGENTFLOW_MODEL_API_KEY`, `AGENTFLOW_MODEL_NAME`, and `AGENTFLOW_MODEL_BASE_URL` in `.env`, then start the stack:

```sh
docker compose --env-file .env -p agentflow -f infra/compose.yml up -d --build
curl -fsS http://localhost:8080/api/health
```

Open `http://localhost:8080` for the English console. The gateway serves the web build at `/`, forwards `/api/` to the Python service, and forwards `/mcp/` with streaming enabled. Redis, Chroma, the API, the web server, and Prometheus stay on the Compose network; only the gateway listens on the host loopback interface by default. The API runs one worker because evaluation jobs, traces, and monitoring summaries are process-local. The API health check waits for Redis and Chroma before the gateway starts.

The default development stack starts without a model key. Health, knowledge, Skills, and diagnostics are available; chat requires `AGENTFLOW_MODEL_API_KEY` and a compatible model configuration. Compose does not automatically load the repository root `.env` when its file is under `infra/`, so pass `--env-file .env` on every Compose command that needs those settings. The Python-only development path remains in the main README and uses `infra/compose.dev.yml` for exposed Redis and Chroma ports.

Stop the complete stack without deleting stored data:

```sh
docker compose -p agentflow -f infra/compose.yml down
```

## Environment

| Variable | Purpose |
| --- | --- |
| `AGENTFLOW_ENV` | `development` for local use; `production` enables mandatory model and bearer-token validation. |
| `AGENTFLOW_MODEL_API_KEY`, `AGENTFLOW_MODEL_NAME`, `AGENTFLOW_MODEL_BASE_URL` | Model credentials, name, and optional compatible endpoint. |
| `AGENTFLOW_EMBEDDING_PROVIDER`, `AGENTFLOW_EMBEDDING_API_KEY`, `AGENTFLOW_EMBEDDING_BASE_URL` | Intent embedding mode and optional online service. |
| `AGENTFLOW_API_TOKENS` | JSON map from bearer tokens to `user_id` and `role`; roles are `admin` and `customer`. |
| `AGENTFLOW_MCP_ALLOWED_HOSTS` | Allowlisted external MCP hosts for a production configuration. |
| `AGENTFLOW_CORS_ORIGINS` | Extra browser origins for direct API access; the Compose console uses `/api` on the same origin. |
| `AGENTFLOW_GATEWAY_BIND`, `AGENTFLOW_GATEWAY_PORT` | Gateway host bind address and port; defaults to `127.0.0.1:8080`. |
| `AGENTFLOW_PROMETHEUS_CONFIG`, `AGENTFLOW_METRICS_TOKEN_FILE` | Prometheus scrape configuration and token file; paths are relative to `infra/`. |

The Compose service supplies its own Redis URL, Chroma host and port, Skills directory, and MCP configuration path. Edit `config/mcp_servers.json` and `skills/` in the checkout, then rebuild and recreate the API image to apply them. Do not put credentials into `VITE_` variables: web build variables are public. The console accepts a bearer token in the Connections view and keeps it only in browser memory until reload.

## Production

Set `AGENTFLOW_ENV=production`, a real model key, and a nonempty `AGENTFLOW_API_TOKENS` JSON map in an untracked `.env` file. Use unique high-entropy tokens. Include a dedicated administrator token for Prometheus. Put only that token in the untracked `infra/prometheus.token` file, set `AGENTFLOW_PROMETHEUS_CONFIG=./prometheus.prod.yml`, and set `AGENTFLOW_METRICS_TOKEN_FILE=./prometheus.token`. The metrics token must also be an `admin` entry in `AGENTFLOW_API_TOKENS`. The production Prometheus job then scrapes `/metrics` using that bearer token. Do not use the tracked example or verification tokens in a production environment.

Keep `AGENTFLOW_SEED_DEMO_DOCS=false` and import approved English knowledge before serving users. The repository's sample knowledge is for development. The gateway listens on loopback by default; place a TLS-terminating reverse proxy in front of it for remote users, or explicitly change `AGENTFLOW_GATEWAY_BIND` in a protected deployment. Configure approved MCP servers and allowlists before enabling external tools. `GET /health` checks required storage, while model and external MCP availability require separate checks in the console and deployment monitoring.

The current token map is a configuration-backed identity mechanism. It does not provide token issuance, revocation, single sign-on, or a user directory. Evaluation jobs, in-process traces, and monitoring counters are not durable across API restarts, so keep a single API worker and export results that must be retained. A production rollout should define retention, external identity, approved knowledge, and model quality thresholds for its target support domain.

## Backup

The named volumes `agentflow_redis_data`, `agentflow_chroma_data`, and `agentflow_prometheus_data` hold conversation receipts, vectors, and Prometheus history. Stop the stack before copying them so the volume snapshots are consistent. For example:

```sh
mkdir -p backups
docker compose -p agentflow -f infra/compose.yml stop
for name in redis_data chroma_data prometheus_data; do
  docker run --rm -v "agentflow_${name}:/source:ro" -v "$(pwd)/backups:/backup" alpine tar czf "/backup/${name}.tgz" -C /source .
done
```

Store the archives and a copy of the untracked deployment configuration and secrets in the organization's approved backup system. The web image and repository assets can be rebuilt; browser memory, queued evaluation jobs, process-local traces, and counters cannot be recovered from these volumes.

## Restore

Restore into stopped volumes using archives from the same compatible image and schema version. On a fresh host, create the three named volumes first. For each archive:

```sh
docker compose -p agentflow -f infra/compose.yml down
docker volume create agentflow_redis_data
docker volume create agentflow_chroma_data
docker volume create agentflow_prometheus_data
for name in redis_data chroma_data prometheus_data; do
  docker run --rm -v "agentflow_${name}:/target" -v "$(pwd)/backups:/backup:ro" alpine sh -c "cd /target && tar xzf /backup/${name}.tgz"
done
docker compose -p agentflow -f infra/compose.yml up -d --build
curl -fsS http://localhost:8080/api/health
```

Restore the matching `.env` and metrics token through the approved secret store before starting production services. Validate a known conversation receipt and a known knowledge document after restore.

## Verification

Run the Python and web suites from the main README. The isolated release check uses a deterministic model fixture, production bearer tokens, a fresh Compose project, and disposable volumes:

```sh
bash scripts/verify_stack.sh
```

It checks gateway and browser assets, health, authorization, knowledge import/upload/search, Skills, new chat, follow-up, duplicate request receipt, mixed routing, tool trace, evaluation polling, MCP status, monitoring, and authorized Prometheus scraping. The script creates a uniquely named verification project and removes only that project's volumes. The fixture demonstrates system wiring; it does not measure answer quality or replace a live-model acceptance run.
