# Release Validation

Stage 8 maps each product requirement to a passing automated check. The local verification stack uses an isolated deterministic model fixture and disposable Redis, Chroma, and Prometheus volumes.

| Requirement | Passing evidence | Remaining acceptance boundary |
| --- | --- | --- |
| FR-01 | `test_stage2_orchestration.py` chat contract; `release_smoke.py` new chat and follow-up. | Validate a selected live model before public use. |
| FR-02 | `test_stage2_orchestration.py` intent and entity cases; `test_stage6_api_cli.py` embedding diagnostics. | Calibrate intent scores on labeled domain data. |
| FR-03 | `test_stage2_orchestration.py` mixed route and escalation; `release_smoke.py` mixed issue. | Measure routing quality on real support cases. |
| FR-04 | `test_stage2_orchestration.py` tool allowlist and schema; `test_stage4_knowledge.py` tool failure cases. | External business systems need their own approval and receipt design. |
| FR-05 | `test_stage4_knowledge.py` replacement and retrieval; `release_smoke.py` import, upload, search, and tool trace. | Replace sample content with approved production knowledge. |
| FR-06 | `test_stage3_memory.py` state switch, compression, and user scope; `release_smoke.py` follow-up. | Set a deployment retention policy. |
| FR-07 | `test_stage3_memory.py` receipts, lease loss, and concurrent turns; `release_smoke.py` duplicate request. | Load-test the selected Redis service and topology. |
| FR-08 | `test_stage2_orchestration.py` escalation; `test_content_assets.py` handoff guidance. | Configure the actual human support channel. |
| FR-09 | `test_stage4_knowledge.py` Skills reload and scoping; `release_smoke.py` status and reload. | Review each business Skill before deployment. |
| FR-10 | `test_stage5_operations.py` evaluation and baseline guards; `web/tests/evaluation.test.mjs` polling; `release_smoke.py` complete job. | Set quality targets from a labeled evaluation set. |
| FR-11 | `test_stage5_operations.py` trace redaction, metrics, cooldown; `release_smoke.py` trace, monitor, and Prometheus. | Define alert thresholds and retention for the target environment. |
| FR-12 | `web/tests/api.test.mjs`, `chatSession.test.mjs`, `evaluation.test.mjs`, and `contract.test.mjs`; headless Chrome console render; `release_smoke.py` gateway assets and API flows. | Run a human browser acceptance pass with the chosen live model and content. |
| FR-13 | `test_stage4_knowledge.py` MCP allowlist and discovery; `test_stage6_api_cli.py` local MCP initialization; `release_smoke.py` status. | Approved external MCP servers are not configured; validate each server after approval. |
| FR-14 | `test_stage8_release.py` English audit and stack contract; `verify_stack.sh` clean project startup; `docs/operations.md` runbook. | Provide TLS termination and a managed secret store for remote production users. |

The current checks establish implementation behavior and deployment wiring. No production accuracy, latency, throughput, or external MCP compatibility claim is made without a measured live evaluation. The stage-specific tests remain the source of truth for functional gates; the release smoke covers their integration through the gateway.
