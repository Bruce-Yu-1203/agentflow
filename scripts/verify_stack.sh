#!/usr/bin/env bash
set -euo pipefail

export AGENTFLOW_GATEWAY_PORT=8082
export AGENTFLOW_PROMETHEUS_CONFIG=./prometheus.prod.yml
export AGENTFLOW_METRICS_TOKEN_FILE=./prometheus.verify.token

project="agentflow-verify-$$"
compose=(docker compose -p "$project" -f infra/compose.yml -f infra/compose.verify.yml)
cleanup() {
  "${compose[@]}" down -v --remove-orphans >/dev/null
}
trap cleanup EXIT

"${compose[@]}" up -d --build
python3 tests/release_smoke.py
