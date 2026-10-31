# AgentFlow Implementation Matrix

> Scope: Python service, English web console, and deployment integration through Stage 8. See [release validation](release-validation.md) for passing checks and environment acceptance boundaries.

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
| FR-01 | `api.app`, `api.contracts` | 1, 6 | New and continuing chat contracts, invalid input |
| FR-02 | `core.intent_recognizer`, `core.embedding` | 2 | Fine intent fusion, provenance, entity extraction, fallback |
| FR-03 | `agents.agent_orchestrator` | 2 | Primary and supporting routing, escalation, partial result |
| FR-04 | `agents.tools`, `mcp.tool_manager` | 2, 4 | Role allowlists, schema rejection, bounded execution |
| FR-05 | `mcp.knowledge_base`, `mcp.retrieval` | 4 | Upsert, stale-chunk removal, evidence, retrieval gate |
| FR-06 | `memory.conversation_memory`, `memory.long_term`, `core.state` | 3 | Current context, task reset, summary and profile isolation |
| FR-07 | `memory.conversation_memory` | 3 | Lease, receipt conflict, atomic commit, safe retry |
| FR-08 | `agents.agent_orchestrator`, `agents.tools` | 2 | Factual handoff without invented ticket acceptance |
| FR-09 | `core.skill_loader` | 4 | Role and keyword matching, reload, malformed file isolation |
| FR-10 | `evaluation.evaluator` | 5 | Metrics, judge errors, progress, compatible baseline |
| FR-11 | `core.operations` | 5 | Redaction, alert thresholds, route penalty and recovery |
| FR-12 | `web` | 7 | Chat, knowledge, evaluation, settings, stale response isolation |
| FR-13 | `mcp.client`, `mcp.server` | 4 | Allowlist, read-only discovery, reconnection, minimal input |
| FR-14 | `cli`, `infra`, `web` | 6–8 | English audit, CLI, Compose and clean-start integration |

## Stage completion evidence

Each stage is committed and pushed after its relevant checks pass. Stages 0–6 leave a runnable or importable Python service at their stated boundary. Stage 7 adds the web console; Stage 8 validates the complete deployment with a deterministic model fixture. Later changes must not silently change public contracts.
