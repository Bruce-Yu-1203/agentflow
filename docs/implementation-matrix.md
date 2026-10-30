# AgentFlow Implementation Matrix

> Scope: Python service through Stage 6. The English web console and release integration remain in Stages 7 and 8.

## Fixed behavior decisions

- The first supported domain is commerce and enterprise software customer support. The six seed documents are development examples, not approved production policies.
- Chat reads conversation context, recognizes intent, then routes. Business intents may invoke knowledge retrieval through an approved role tool. Greeting, feedback, handoff, and unknown intent do not invoke RAG during chat. The explicit `/search` diagnostic endpoint may search any valid query.
- Agent execution supports a primary role and concurrent supporting roles. Roles have distinct missions, input and output contracts, tool allowlists, handoff conditions, and observable results.
- Failure of optional episodic memory, profile lookup, or knowledge retrieval may produce a reduced-context answer with a visible trace. Failure of the Redis conversation lease or receipt store stops the turn because ordering and retry guarantees cannot be preserved.
- Evaluation results distinguish intent metrics, dialog quality, and a separately labeled RAG retrieval suite. No benchmark result is claimed before it is measured on AgentFlow.
- Production configuration requires authentication, approved knowledge, a reachable vector service, and explicit secrets. Development may use local vector storage and demonstration assets.

## Requirement coverage

| Requirement | Target module | Stage | Verification gate |
| --- | --- | --- | --- |
| FR-01 | `api.main`, request and response models | 1, 6 | New and continuing chat contracts, invalid input |
| FR-02 | `core.intent` and `core.embedding` | 2 | Fine intent fusion, provenance, entity extraction, fallback |
| FR-03 | `agents.orchestrator` | 2 | Primary and supporting routing, escalation, partial result |
| FR-04 | `agents.tools`, `tooling.manager` | 2, 4 | Role allowlists, schema rejection, bounded execution |
| FR-05 | `tooling.knowledge`, `tooling.rag` | 4 | Upsert, stale-chunk removal, evidence, retrieval gate |
| FR-06 | `memory.store`, `core.state` | 3 | Current context, task reset, summary and profile isolation |
| FR-07 | `memory.store`, `core.concurrency` | 3 | Lease, receipt conflict, atomic commit, safe retry |
| FR-08 | `agents.escalation` | 2 | Factual handoff without invented ticket acceptance |
| FR-09 | `core.skills` | 4 | Role and keyword matching, reload, malformed file isolation |
| FR-10 | `evaluation.runner`, `evaluation.jobs` | 5 | Metrics, judge errors, progress, compatible baseline |
| FR-11 | `monitor.metrics`, `core.trace` | 5 | Redaction, alert thresholds, route penalty and recovery |
| FR-12 | `web` | 7 | Chat, knowledge, evaluation, settings, stale response isolation |
| FR-13 | `tooling.mcp_client`, `tooling.mcp_server` | 4 | Allowlist, read-only discovery, reconnection, minimal input |
| FR-14 | `api.cli`, `infra`, `web` | 6–8 | English audit, CLI, Compose and clean-start integration |

## Stage completion evidence

For each stage, record the commit and push after its relevant checks pass. Stages 0–6 must leave a runnable or importable Python service at their stated boundary. A stage is complete only when its listed verification gate passes; later stages may expand earlier modules without changing their public contracts silently.
