# NeuroFlow Architecture Runbook

This runbook provides incident response guidelines for the 5 most critical production scenarios identified for the NeuroFlow platform. It is designed to assist on-call engineers in quickly diagnosing and remediating production outages.

## Incident 1 — High query latency (P95 > 10s)

**Symptoms:**
- The `/query` endpoint consistently takes longer than 10 seconds to return the first token or final result.
- Upstream systems experience timeouts.

**Check:**
- **Jaeger Traces:** Open Jaeger UI and check which span is slow. Is it `ingestion.process`, `llm.call`, `vector_search`, or the retrieval steps?
- **Redis Cache:** Check Redis memory usage and cache hit rate in the Grafana dashboard. Low hit rates indicate excessive DB querying.
- **Postgres Performance:** Run `SELECT * FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 5;` to see what queries are bottlenecking the DB.

**Remediation:**
1. **Flush Redis Cache:** If degraded state, flush the query cache `redis-cli flushall`.
2. **Add Indexes:** If `pg_stat_statements` shows sequential scans on chunks, verify `hnsw` indexes are intact.
3. **Scale API Replicas:** If CPU/Memory on the FastAPI pods is maxed out, scale up the `API` replica count horizontally.

---

## Incident 2 — Evaluation scores degrading

**Symptoms:**
- Automated pipelines show decreasing moving averages for `faithfulness`, `relevance`, or `context_precision`.
- High volume of negative human ratings on recent runs.

**Check:**
- Which specific pipeline version and configuration are the degrading scores tied to? Check `/pipelines/{id}/analytics`.
- **Recent Ingestion Quality:** Have low-quality, raw log files or highly ambiguous URLs been ingested recently? (Low-quality input → low-quality retrieval).
- **MLflow:** Did a recent background job automatically deploy a new fine-tuned model via MLflow replacing the stable version?

**Remediation:**
1. **Revert Model:** Revert the last fine-tuned model to the previous stable alias in MLflow or roll back the Pipeline JSON configuration.
2. **Inspect/Purge Training Data:** Query the `/chunks` API to find recent low-quality documents and `ARCHIVE` or `DELETE` those document embeddings.

---

## Incident 3 — LLM provider circuit breaker open

**Symptoms:**
- API returns `503 Service Unavailable` for Queries.
- `/health` endpoint shows `circuit_breaker: open` instead of `closed`.

**Check:**
- **Health Check Status:** Use `curl https://production-api/health` to confirm the Circuit Breaker is indeed OPEN.
- **Provider Status Pages:** Check OpenAI, Anthropic, or the respective API provider status pages for ongoing, widespread outages.
- **Quota:** Verify API keys have not exceeded their monthly cost tier limits.

**Remediation:**
1. **Wait for Timeout:** The circuit breaker is designed to auto-transition to `HALF_OPEN` after its recovery timeout.
2. **Manual Reset:** If the provider issue is resolved, manually reset the breaker via `POST /admin/circuit-breaker/reset`.
3. **Failover:** If down indefinitely, patch the pipeline config (`generation.model_routing.provider`) to a fallback provider (e.g. from OpenAI to Anthropic).

---

## Incident 4 — Ingestion queue depth > 100

**Symptoms:**
- Newly uploaded documents stay in the `status: processing` state for extended periods.

**Check:**
- **Queue Depth:** Review the `/health` endpoint or Redis raw metrics to verify the task queue depth.
- **Worker Logs:** Check the background worker process (`arq` or raw Python worker) container logs. Look for Python exceptions or OOM (Out of Memory) kills.

**Remediation:**
1. **Restart Workers:** Restart the background worker containers to clear any hung connections. `docker compose restart worker`.
2. **Clear Stuck Jobs:** Check Redis for dead letter queues or indefinitely stuck job locks and clear them.
3. **Scale Workers:** Increase parallel processing capabilities if standard load has organically increased.

---

## Incident 5 — Database disk usage > 80%

**Symptoms:**
- Disk alarms trigger.
- Postgres refuses to ingest new documents, returning standard `PGError: disk full`.

**Check:**
- **Table Sizes:** Run `SELECT relname as table, pg_size_pretty(pg_total_relation_size(relid)) FROM pg_catalog.pg_statio_user_tables ORDER BY pg_total_relation_size(relid) DESC;` to find which table is growing fastest.
- **Cleanup job status:** Check application logs for the `APScheduler` daily data retention run. Verify if old evaluations and runs are actually being cleaned up.

**Remediation:**
1. **Trigger Manual Cleanup:** Run the data retention script manually.
2. **Expand Volume:** Scale the Postgres EBS/Cloud Volume configuration.
3. **Review Retention Policies:** Reduce the days kept from 90/180 to shorter spans if disk accumulation exceeds budget.
