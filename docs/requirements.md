# AgentFlow Product Requirements

> Version: 0.1 draft | Updated: 2026-10-30

## 1. Purpose and Status

This document defines the target scope and acceptance criteria for AgentFlow. The repository includes a Python API runtime, CLI, and tests for the Stage 0–6 path; [implementation status](implementation-status.md) distinguishes implemented behavior from remaining work. The companion [technical design](technical-design.md) records the implementation approach and staged path.

The first release focuses on a customer-support workflow: understand a request, route it to the right specialist, use approved tools and knowledge, preserve conversation context, and return a traceable result. Product-specific policies, model providers, identity systems, and business integrations must be selected during implementation.

## 2. Goals and Users

### Goals

1. Identify a customer's intent and route each request to a suitable role.
2. Support multi-turn conversations without asking customers to repeat known details.
3. Ground answers in approved knowledge and constrained tools.
4. Handle retries, concurrent requests, and model or tool failures with explicit outcomes.
5. Give operators ways to maintain knowledge and business rules, inspect runtime behavior, and evaluate answer quality.

### Users

| User | Needs |
| --- | --- |
| Customer | Ask general, technical, or billing questions; continue a conversation; request human support. |
| Support operator or administrator | Maintain knowledge and handling rules; inspect traces, monitoring, and evaluations. |
| Integrator | Call the chat API and connect model providers, external tools, and future business systems. |

### Example journey

A customer reports that sign-in returns HTTP 401 and a payment may have been charged twice. The system identifies both technical and billing concerns, selects a primary role and a supporting role, and combines their results into one reply. On the next turn, the customer provides an order number; the system continues the same conversation and carries forward valid fields. If the client loses the response, it retries with the same message ID and receives the saved result without duplicating the conversation entry.

## 3. Functional Requirements

Priority: **P0** is required for the initial end-to-end workflow. **P1** follows once that workflow is stable. Acceptance criteria describe observable behavior and do not imply that the current repository already implements it.

| ID | Priority | Requirement | Acceptance criteria |
| --- | --- | --- | --- |
| FR-01 | P0 | Provide a chat endpoint that accepts a message, user, conversation, and client message ID and returns the answer, conversation ID, execution ID, status, and routing details. | A new conversation returns a reusable ID; a later request continues it; empty or oversized messages are rejected. |
| FR-02 | P0 | Combine language-model, vector, and rule-based signals to identify intent, domain, urgency, and entities. | The response exposes intent signals and the vector source; vector failures fall back without mixing incompatible vector spaces. |
| FR-03 | P0 | Route between General, Technical, Billing, and Escalation roles; allow primary and supporting roles to work in parallel on mixed requests. | Single-domain requests choose a suitable role; mixed requests record roles and reasons; urgent requests and explicit handoff requests use the escalation path. |
| FR-04 | P0 | Give each role only its approved deterministic tools and validate every tool input. | Unauthorized tools and invalid arguments are rejected; technical and billing tools state their evidence and limits. |
| FR-05 | P0 | Import, update, count, and search knowledge documents; permit on-demand retrieval for business intents and skip it for greeting, feedback, handoff, and unknown intent. | Reimporting the same document identity replaces obsolete chunks; results retain document identity and version; retrieval failures are never presented as verified policy. |
| FR-06 | P0 | Preserve recent messages, summaries, user profiles, and structured business fields, with rules for inheritance and clearing stale fields. | Follow-up turns can use valid known fields; switching order or business domain clears stale fields; optional history or profile failure degrades without losing the current turn; summary failures do not discard uncompressed messages. |
| FR-07 | P0 | Serialize requests within a conversation and provide receipts for safe retries. | The same message ID and content return the saved result; reusing an ID with different content returns a conflict; same-conversation requests observe committed order; failures specify retryability. |
| FR-08 | P0 | Produce a useful human handoff summary without claiming that a ticket was created or an agent accepted the case. | The reply summarizes the request and known details and tells the customer how to reach the actual support channel. |
| FR-09 | P1 | Store changing business rules as Skills files that can be matched by role or keywords and reloaded at runtime. | Administrators can inspect load status, parsing errors, and reload results; rule text cannot grant tool permissions. |
| FR-10 | P1 | Run intent and multi-turn conversation evaluations asynchronously and report progress and results. | A job ID is returned; reports separate valid results from evaluation errors and include intent metrics, business assertions, and conversation-quality scores; regression checks compare only compatible suites. |
| FR-11 | P1 | Expose health, performance metrics, tool traces, and degraded runtime state. | An execution ID retrieves a redacted trace; monitoring shows recent success rates, latency, and tool failures; repeated specialist failures can reduce routing preference and trigger recovery probes. |
| FR-12 | P1 | Provide a web console for chat, conversation switching, knowledge import and search, runtime inspection, and evaluation. | Users can complete a chat and inspect role and tool details; responses from an old request cannot overwrite the current conversation state; credentials are not embedded in public build variables. |
| FR-13 | P1 | Connect approved read-only external tools through MCP and expose local knowledge search to other MCP clients. | Configuration limits servers, tools, roles, and read-only behavior; connection status is visible; external calls receive only the parameters they need. |
| FR-14 | P1 | Ship an English-language web console, CLI, configuration, examples, and deployment stack for the Python service. | All user-facing labels, prompts, errors, sample data, operator logs, API descriptions, documentation, and code comments use English; the complete stack starts through a documented Compose configuration. |

## 4. Non-Functional Requirements

| Area | Requirement |
| --- | --- |
| Security | Production requires server-side authentication and separate customer and administrator permissions. Model keys, MCP credentials, and personal data must not appear in public frontend variables or unredacted traces. |
| Reliability | Use a 50-second overall chat budget and 24-hour message receipts as initial design values. Timeouts, lost locks, partial results, and failures must have explicit outcomes. Before adding side-effecting tools, implement pre-operation receipts, downstream idempotency keys, and result lookup. |
| Data isolation | Scope conversations, receipts, profiles, and retrieval by identity. Demonstration content must never be seeded into production knowledge. |
| Observability | Assign an execution ID to each turn and record stage latency and error categories. A successful model call does not establish that its answer is correct. |
| Quality | Measure intent Accuracy and Macro-F1 on a labeled set; evaluate conversations with business assertions and quality scores. Do not promise an accuracy threshold before a representative baseline exists. |
| Input limits | Initial API limits should be explicit. A useful starting point is 1–12,000 characters per message, 10 MB per knowledge upload, and a retrieval `top_k` between 1 and 20. |

## 5. Delivery Scope

1. **Core workflow (P0):** API, four roles, intent recognition and routing, read-only tools, knowledge retrieval, multi-turn memory, retry safety, and handoff messaging.
2. **Full product (P1):** Skills, monitoring and traces, asynchronous evaluations, MCP, an English-language CLI and web console, and a complete deployment stack for the Python service.
3. **Business integrations:** Order lookup, payment verification, refund execution, ticket creation, and agent queues require real systems, permissions, and audit support before they can be offered.

The full product targets one Python backend and its web console. Production traffic, an availability SLA, and a labeled quality baseline have not been established; define those targets after a representative pilot.

## 6. Decisions Needed Before Production

Select the target industry and knowledge content, model provider, deployment environment, identity provider, data-retention policy, quality targets, and whether real ticketing or payment integrations are required. These choices affect cost, access control, data handling, and acceptance testing.
