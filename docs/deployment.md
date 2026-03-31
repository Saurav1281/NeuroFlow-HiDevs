# NeuroFlow Deployment Guide: Railway

This document provides step-by-step instructions for deploying NeuroFlow to Railway.

## 1. Project Setup

1.  **Install Railway CLI**:
    ```bash
    npm i -g @railway/cli
    ```
2.  **Login**:
    ```bash
    railway login
    ```
3.  **Initialize Project**:
    ```bash
    railway init
    ```

## 2. Infrastructure Services

### Managed PostgreSQL (with pgvector)
1.  Click **"New"** -> **"Database"** -> **"Add PostgreSQL"**.
2.  Once created, go to the **Variables** tab and copy the `DATABASE_URL`.
3.  NeuroFlow requires `pgvector`. Railway's Postgres 15+ images include it by default.

### Managed Redis
1.  Click **"New"** -> **"Database"** -> **"Add Redis"**.
2.  Copy the `REDIS_URL` from the **Variables** tab.

## 3. Application Services

### API (Backend)
1.  Click **"New"** -> **"GitHub Repo"** -> Select your repo.
2.  Service Name: `api`.
3.  **Root Directory**: `/backend`.
4.  **Environment Variables**:
    *   Set all variables from `.env.example`.
    *   `DATABASE_URL`: `${{Postgres.DATABASE_URL}}`
    *   `REDIS_URL`: `${{Redis.REDIS_URL}}`
    *   `PORT`: `8000`

### Worker
1.  Create another service from the same repo.
2.  Service Name: `worker`.
3.  **Root Directory**: `/backend`.
4.  **Custom Command**: `python -m backend.worker`.
5.  **Environment Variables**: Same as API.

### Frontend
1.  Create another service from the same repo.
2.  Service Name: `frontend`.
3.  **Root Directory**: `/frontend`.
4.  **Environment Variables**:
    *   `NEXT_PUBLIC_API_URL`: Use the public URL of the `api` service.

## 4. Monitoring & MLflow

### MLflow
1.  Deploy a Docker-based service using the image `ghcr.io/mlflow/mlflow:latest`.
2.  Command: `mlflow server --host 0.0.0.0 --port 5000 --backend-store-uri ${{Postgres.DATABASE_URL}} --artifacts-destination s3://your-bucket`.
3.  Expose Port `5000`.

### Prometheus & Jaeger
1.  Deploy using their respective Docker images or Railway templates.
2.  Configure `api` to point to the `OTEL_EXPORTER_OTLP_ENDPOINT`.

---

## 5. Production Verification Checklist

Follow these steps once services are green:

- [ ] **Health Check**: `GET https://your-api.railway.app/health`
    - *Expected*: `{"status": "ok", "checks": {"postgres": true, "redis": true, "mlflow": true}}`
- [ ] **Document Ingestion**:
    ```bash
    curl -X POST -F "file=@tests/fixtures/test_doc.pdf" https://your-api.railway.app/ingest
    ```
    - *Expected*: `201 Created`, status reaches `complete`.
- [ ] **RAG Query**:
    ```bash
    curl -X POST -H "Content-Type: application/json" -d '{"query": "What is NeuroFlow?"}' https://your-api.railway.app/query
    ```
    - *Expected*: Response with cited answer.
- [ ] **Streaming Verification**:
    - Observe tokens arriving progressively in the UI or via `curl --no-buffer`.
- [ ] **MLflow Visibility**:
    - Access `https://your-mlflow.railway.app` and verify experiments are logged.
- [ ] **Load Test**:
    ```bash
    locust -f backend/tests/performance/locustfile.py -H https://your-api.railway.app --headless -u 10 -r 2 --run-time 2m
    ```
    - Document results in a `load_test_results.txt` file.

---

## 6. Rollback Procedure

### Redeply Previous Image
1.  Go to the service in Railway Dashboard.
2.  Navigate to the **Deployments** tab.
3.  Find the previous successful deployment and click **"Redeploy"**.

### Database Migrations
If a deployment involved a schema change that broke prod:
1.  Connect to the DB via `railway connect`.
2.  Run migration reversal (if using Alembic): `alembic downgrade -1`.
3.  Verify system stability.

### Verification of Success
1.  Check `/health` endpoint.
2.  Run E2E ingestion test.
