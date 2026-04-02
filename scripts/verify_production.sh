#!/usr/bin/env bash
# NeuroFlow Production Verification Script
# Usage: ./scripts/verify_production.sh <BASE_URL> [AUTH_TOKEN]
# Example: ./scripts/verify_production.sh https://neuroflow-api.railway.app eyJhbG...

set -euo pipefail

BASE_URL="${1:?Usage: $0 <BASE_URL> [AUTH_TOKEN]}"
TOKEN="${2:-}"
PASS=0
FAIL=0
TOTAL=0

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

header() {
  echo ""
  echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${CYAN}  NeuroFlow Production Verification${NC}"
  echo -e "${CYAN}  Target: ${BASE_URL}${NC}"
  echo -e "${CYAN}  Date:   $(date -u +%Y-%m-%dT%H:%M:%SZ)${NC}"
  echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo ""
}

auth_header() {
  if [ -n "$TOKEN" ]; then
    echo "-H" "Authorization: Bearer $TOKEN"
  fi
}

check() {
  local name="$1"
  local result="$2"
  TOTAL=$((TOTAL + 1))
  if [ "$result" -eq 0 ]; then
    PASS=$((PASS + 1))
    echo -e "  ${GREEN}✅ PASS${NC}  $name"
  else
    FAIL=$((FAIL + 1))
    echo -e "  ${RED}❌ FAIL${NC}  $name"
  fi
}

header

# ── 1. Health Check ─────────────────────────────────────────────
echo -e "${YELLOW}[1/7] Health Check${NC}"
HTTP_CODE=$(curl -s -o /tmp/nf_health.json -w "%{http_code}" "${BASE_URL}/health")
if [ "$HTTP_CODE" = "200" ]; then
  echo "       Response: $(cat /tmp/nf_health.json)"
  check "GET /health returns 200" 0
else
  echo "       HTTP $HTTP_CODE"
  check "GET /health returns 200" 1
fi

# ── 2. Document Ingestion ──────────────────────────────────────
echo -e "${YELLOW}[2/7] Document Ingestion${NC}"
if [ -f "tests/fixtures/test_doc.pdf" ]; then
  INGEST_CODE=$(curl -s -o /tmp/nf_ingest.json -w "%{http_code}" \
    -X POST $(auth_header) \
    -F "file=@tests/fixtures/test_doc.pdf" \
    "${BASE_URL}/ingest")
  echo "       Response: $(cat /tmp/nf_ingest.json)"
  [ "$INGEST_CODE" = "201" ] || [ "$INGEST_CODE" = "200" ]
  check "POST /ingest returns 2xx" $?
else
  echo "       ⚠ tests/fixtures/test_doc.pdf not found, skipping"
  check "POST /ingest (skipped — no fixture)" 1
fi

# ── 3. RAG Query ───────────────────────────────────────────────
echo -e "${YELLOW}[3/7] RAG Query${NC}"
QUERY_CODE=$(curl -s -o /tmp/nf_query.json -w "%{http_code}" \
  -X POST $(auth_header) \
  -H "Content-Type: application/json" \
  -d '{"query": "What is discussed in the test document?"}' \
  "${BASE_URL}/query")
echo "       Response (truncated): $(cat /tmp/nf_query.json | head -c 300)"
[ "$QUERY_CODE" = "200" ]
check "POST /query returns 200 with answer" $?

# ── 4. Evaluations ─────────────────────────────────────────────
echo -e "${YELLOW}[4/7] Evaluations${NC}"
EVAL_CODE=$(curl -s -o /tmp/nf_eval.json -w "%{http_code}" \
  $(auth_header) \
  "${BASE_URL}/evaluations")
echo "       Response (truncated): $(cat /tmp/nf_eval.json | head -c 300)"
[ "$EVAL_CODE" = "200" ]
check "GET /evaluations returns 200" $?

# ── 5. Streaming ───────────────────────────────────────────────
echo -e "${YELLOW}[5/7] Streaming${NC}"
STREAM_CODE=$(curl -s -o /tmp/nf_stream.txt -w "%{http_code}" \
  --max-time 10 --no-buffer \
  $(auth_header) \
  "${BASE_URL}/query/test/stream" 2>/dev/null || echo "000")
if [ "$STREAM_CODE" = "200" ]; then
  check "GET /query/{id}/stream returns 200" 0
else
  echo "       HTTP $STREAM_CODE (may require valid run_id)"
  check "GET /query/{id}/stream returns 200" 1
fi

# ── 6. Prometheus Metrics ──────────────────────────────────────
echo -e "${YELLOW}[6/7] Prometheus Metrics${NC}"
METRICS_CODE=$(curl -s -o /tmp/nf_metrics.txt -w "%{http_code}" "${BASE_URL}/metrics")
if [ "$METRICS_CODE" = "200" ]; then
  METRIC_COUNT=$(wc -l < /tmp/nf_metrics.txt)
  echo "       ${METRIC_COUNT} lines of metrics"
  check "GET /metrics returns Prometheus data" 0
else
  echo "       HTTP $METRICS_CODE"
  check "GET /metrics returns Prometheus data" 1
fi

# ── 7. MLflow ──────────────────────────────────────────────────
echo -e "${YELLOW}[7/7] MLflow${NC}"
MLFLOW_URL="${MLFLOW_URL:-${BASE_URL%/*}/mlflow}"
MLFLOW_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "${MLFLOW_URL}" 2>/dev/null || echo "000")
if [ "$MLFLOW_CODE" = "200" ]; then
  check "MLflow dashboard accessible" 0
else
  echo "       HTTP $MLFLOW_CODE at $MLFLOW_URL (set MLFLOW_URL env var if different)"
  check "MLflow dashboard accessible" 1
fi

# ── Summary ────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  Results: ${GREEN}${PASS} passed${NC} / ${RED}${FAIL} failed${NC} / ${TOTAL} total"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
