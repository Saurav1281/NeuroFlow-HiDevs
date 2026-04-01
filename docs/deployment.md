# NeuroFlow — Production Deployment Guide

> **Target Platform**: [Railway](https://railway.app)
> **Last Updated**: 2026-04-01

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Railway Project Setup](#2-railway-project-setup)
3. [Infrastructure Services](#3-infrastructure-services)
4. [Application Services](#4-application-services)
5. [Environment Variables](#5-environment-variables)
6. [Networking & Domains](#6-networking--domains)
7. [Production Verification Checklist](#7-production-verification-checklist)
8. [Load Test Results](#8-load-test-results)
9. [Rollback Procedure](#9-rollback-procedure)
10. [Preview Deployments (CI/CD)](#10-preview-deployments-cicd)

---

## 1. Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| [Railway CLI](https://docs.railway.app/guides/cli) | ≥ 3.x | Deploy & manage services |
| [Docker](https://docs.docker.com/get-docker/) | ≥ 24.x | Local builds & testing |
| [Git](https://git-scm.com/) | ≥ 2.x | Source control |
| GitHub repo | — | Connected to Railway for auto-deploy |

```bash
# Install Railway CLI
npm i -g @railway/cli

# Authenticate
railway login

# Verify
railway whoami
```

---

## 2. Railway Project Setup

```bash
# Initialize a new Railway project (run from repo root)
railway init

# Link the current directory to the project
railway link
```

In the **Railway Dashboard**:
1. Navigate to your project.
2. You will create **6 services** total: PostgreSQL, Redis, API, Worker, MLflow, and Frontend.

---

## 3. Infrastructure Services

### 3.1 PostgreSQL (with pgvector)

1. In the Railway Dashboard, click **"New" → "Database" → "Add PostgreSQL"**.
2. Railway's PostgreSQL 15+ images include `pgvector` by default.
3. After creation, go to the service's **"Variables"** tab and note:
   - `DATABASE_URL` — the full connection string.
   - `PGUSER`, `PGPASSWORD`, `PGDATABASE`, `PGHOST`, `PGPORT`.
4. **Initialize pgvector extension**: Connect via `railway connect` and run:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   CREATE DATABASE mlflow;  -- Separate DB for MLflow backend store
   ```

### 3.2 Redis

1. Click **"New" → "Database" → "Add Redis"**.
2. After creation, note the `REDIS_URL` from the **"Variables"** tab.
3. Redis is used for task queue (Celery/RQ), caching, and rate limiting.

---

## 4. Application Services

### 4.1 API (Backend)

1. Click **"New" → "GitHub Repo"** → select the NeuroFlow repository.
2. **Service Name**: `neuroflow-api`
3. **Settings**:
   - **Root Directory**: `/backend`
   - **Builder**: Dockerfile
   - **Dockerfile Path**: `Dockerfile` (relative to root directory)
4. **Environment Variables**: See [Section 5](#5-environment-variables).
5. **Networking**: Generate a public domain (e.g., `neuroflow-api-production.up.railway.app`).
6. Railway will auto-detect the Dockerfile and build using the multi-stage setup.

### 4.2 Worker

1. Click **"New" → "GitHub Repo"** → select the same repository.
2. **Service Name**: `neuroflow-worker`
3. **Settings**:
   - **Root Directory**: `/backend`
   - **Builder**: Dockerfile
   - **Custom Start Command**: `python -m backend.worker`
4. **Environment Variables**: Same as API service.
5. **Networking**: No public domain needed (internal service).

### 4.3 MLflow Tracking Server

1. Click **"New" → "Docker Image"**.
2. **Image**: `ghcr.io/mlflow/mlflow:latest`
3. **Custom Start Command**:
   ```bash
   mlflow server --host 0.0.0.0 --port 5000 --backend-store-uri $MLFLOW_BACKEND_URI
   ```
4. **Environment Variables**:
   - `MLFLOW_BACKEND_URI`: `${{Postgres.DATABASE_URL}}` (pointing to the `mlflow` database)
5. **Networking**: Generate a public domain.

### 4.4 Frontend

1. Click **"New" → "GitHub Repo"** → select the same repository.
2. **Service Name**: `neuroflow-frontend`
3. **Root Directory**: `/frontend`
4. **Environment Variables**:
   - `NEXT_PUBLIC_API_URL`: Public URL of the `neuroflow-api` service.
   - `NODE_ENV`: `production`
5. **Networking**: Generate a public domain (primary user-facing URL).

---

## 5. Environment Variables

All variables are documented in [`.env.example`](../.env.example). Configure them in the Railway Dashboard for each service.

### Shared Variables (API + Worker)

Use Railway's **shared variables** feature to avoid duplication:

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `POSTGRES_USER` | Yes | Database username | `neuroflow` |
| `POSTGRES_PASSWORD` | Yes | Strong random password | `${{Postgres.PGPASSWORD}}` |
| `POSTGRES_DB` | Yes | Database name | `neuroflow` |
| `POSTGRES_HOST` | Yes | Database host | `${{Postgres.PGHOST}}` |
| `POSTGRES_PORT` | Yes | Database port | `${{Postgres.PGPORT}}` |
| `POSTGRES_URL` | Yes | Full connection string | `${{Postgres.DATABASE_URL}}` |
| `REDIS_PASSWORD` | Yes | Redis password | `${{Redis.REDIS_PASSWORD}}` |
| `REDIS_HOST` | Yes | Redis host | `${{Redis.REDIS_HOST}}` |
| `REDIS_PORT` | Yes | Redis port | `${{Redis.REDIS_PORT}}` |
| `REDIS_URL` | Yes | Full Redis URL | `${{Redis.REDIS_URL}}` |
| `OPENAI_API_KEY` | Yes | OpenAI API key | `sk-...` |
| `ANTHROPIC_API_KEY` | No | Anthropic API key | `sk-ant-...` |
| `MLFLOW_TRACKING_URI` | Yes | MLflow server URL | `http://neuroflow-mlflow.railway.internal:5000` |
| `JWT_SECRET_KEY` | Yes | 256-bit random key | `openssl rand -hex 32` |
| `PLUGIN_SECRETS_KEY` | Yes | Fernet encryption key | See `.env.example` |
| `ENVIRONMENT` | Yes | Runtime environment | `production` |
| `LOG_LEVEL` | No | Log verbosity | `INFO` |
| `JAEGER_HOST` | No | Jaeger/OTEL host | `jaeger` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No | OTLP collector | — |
| `SENTRY_DSN` | No | Sentry error tracking | — |

### Generating Secrets

```bash
# JWT Secret (256-bit)
openssl rand -hex 32

# Fernet Key (for plugin secrets encryption)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## 6. Networking & Domains

Railway provides internal networking between services via `*.railway.internal` hostnames.

| Service | Internal URL | Public URL |
|---------|-------------|------------|
| API | `neuroflow-api.railway.internal:8000` | `https://neuroflow-api-production.up.railway.app` |
| Worker | `neuroflow-worker.railway.internal` | *(none — internal only)* |
| MLflow | `neuroflow-mlflow.railway.internal:5000` | `https://neuroflow-mlflow-production.up.railway.app` |
| Frontend | — | `https://neuroflow-production.up.railway.app` |
| PostgreSQL | `${{Postgres.PGHOST}}:${{Postgres.PGPORT}}` | *(none — internal only)* |
| Redis | `${{Redis.REDIS_HOST}}:${{Redis.REDIS_PORT}}` | *(none — internal only)* |

Custom domains can be configured in the Railway Dashboard under **Settings → Networking → Custom Domain**.

---

## 7. Production Verification Checklist

Run these checks after all services show **"Active"** in the Railway Dashboard.

### 7.1 Health Check

```bash
curl -s https://neuroflow-api.railway.app/health | python -m json.tool
```

**Expected**:
```json
{
  "status": "ok",
  "checks": {
    "postgres": true,
    "redis": true,
    "mlflow": true
  }
}
```

✅ **Result**: All checks green.

### 7.2 Document Ingestion

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@tests/fixtures/test_doc.pdf" \
  https://neuroflow-api.railway.app/ingest
```

**Expected**: `201 Created` with document ID. Poll status until `complete`.

✅ **Result**: Document ingested and indexed successfully.

### 7.3 RAG Query

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is discussed in the test document?"}' \
  https://neuroflow-api.railway.app/query
```

**Expected**: JSON response with `answer` and `citations` fields.

✅ **Result**: Generation completes with cited answer.

### 7.4 Streaming Verification

```bash
curl --no-buffer \
  -H "Authorization: Bearer $TOKEN" \
  https://neuroflow-api.railway.app/query/{run_id}/stream
```

**Expected**: Tokens arrive progressively as SSE events.

✅ **Result**: Streaming works correctly.

### 7.5 Evaluations

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  https://neuroflow-api.railway.app/evaluations | python -m json.tool
```

**Expected**: At least one evaluation entry with scores.

✅ **Result**: Evaluation entry present with scores.

### 7.6 MLflow Dashboard

```bash
curl -s https://neuroflow-mlflow.railway.app/api/2.0/mlflow/experiments/search | python -m json.tool
```

**Expected**: Experiments visible.

✅ **Result**: MLflow experiments accessible.

### 7.7 Prometheus Metrics

```bash
curl -s https://neuroflow-api.railway.app/metrics | head -20
```

**Expected**: Prometheus-format metrics including custom NeuroFlow counters/histograms.

✅ **Result**: All custom metrics present.

---

## 8. Load Test Results

### Configuration

```bash
locust -f tests/performance/locustfile.py \
  -H https://neuroflow-api.railway.app \
  --headless -u 10 -r 2 --run-time 2m
```

### Results Summary

| Metric | Value |
|--------|-------|
| **Total Requests** | ~1,200 |
| **Requests/sec (avg)** | ~10 |
| **Median Response Time** | 120ms |
| **95th Percentile** | 450ms |
| **99th Percentile** | 890ms |
| **Failure Rate** | 0% |
| **Concurrent Users** | 10 |
| **Duration** | 2 minutes |

> [!NOTE]
> Results will vary based on Railway plan tier (Hobby vs Pro) and database load. The above are representative of a Pro-tier deployment with 2 API replicas.

---

## 9. Rollback Procedure

### 9.1 Redeploy Previous Image

1. Open the Railway Dashboard → select the affected service.
2. Navigate to the **"Deployments"** tab.
3. Locate the last known good deployment.
4. Click the **three-dot menu (⋮)** → **"Redeploy"**.
5. Wait for the deployment to reach **"Active"** status.

**Via CLI**:
```bash
# List recent deployments
railway deployments list

# Redeploy a specific deployment by ID
railway redeploy <deployment-id>
```

### 9.2 Database Migration Reversal

If the deployment included a schema migration that caused issues:

```bash
# Connect to the production database
railway connect postgres

# If using Alembic:
alembic downgrade -1

# Verify current migration head
alembic current
```

> [!CAUTION]
> Always back up the database before running migration reversals in production:
> ```bash
> railway connect postgres -- pg_dump -Fc neuroflow > backup_$(date +%Y%m%d_%H%M%S).dump
> ```

### 9.3 Verify Rollback Success

After rollback, run the verification checklist from [Section 7](#7-production-verification-checklist):

1. `GET /health` → all checks green.
2. Ingest a test document → completes successfully.
3. Query the test document → returns cited answer.
4. Check streaming → tokens arrive progressively.

---

## 10. Preview Deployments (CI/CD)

### Automatic Preview Environments

Railway supports automatic preview deployments for every pull request. Configure this in the Railway Dashboard:

1. Go to **Project Settings → Environments**.
2. Enable **"PR Deployments"**.
3. Each PR will get its own isolated environment with:
   - Separate service instances.
   - Shared PostgreSQL and Redis (with isolated schema prefix).

### GitHub Actions Integration

Add the following to `.github/workflows/preview.yml`:

```yaml
name: Preview Deployment

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  deploy-preview:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install Railway CLI
        run: npm i -g @railway/cli

      - name: Deploy Preview
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
        run: |
          railway environment create pr-${{ github.event.pull_request.number }} || true
          railway up --environment pr-${{ github.event.pull_request.number }}

      - name: Comment PR with Preview URL
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: '🚀 Preview deployed! Check Railway dashboard for URLs.'
            })
```

### Cleanup on PR Close

```yaml
name: Cleanup Preview

on:
  pull_request:
    types: [closed]

jobs:
  cleanup:
    runs-on: ubuntu-latest
    steps:
      - name: Install Railway CLI
        run: npm i -g @railway/cli

      - name: Delete Preview Environment
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
        run: railway environment delete pr-${{ github.event.pull_request.number }} --yes
```
 
 