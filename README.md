# NeuroFlow

NeuroFlow is an advanced RAG (Retrieval-Augmented Generation) platform for enterprise document intelligence.

## Production Status

| Service | Status | URL |
|---------|--------|-----|
| API | 🟢 Live | [https://neuroflow-api.railway.app](https://neuroflow-api.railway.app) |
| Frontend | 🟢 Live | [https://neuroflow.railway.app](https://neuroflow.railway.app) |
| Monitoring | 🟡 Restricted | [https://mlflow.railway.app](https://mlflow.railway.app) |

## Quick Start

1.  **Deployment**: See [docs/deployment.md](docs/deployment.md) for Railway instructions.
2.  **Environment**: Copy `.env.example` to `.env` and fill in secrets.
3.  **Local Dev**:
    ```bash
    docker compose up
    ```

## Features

-   **Multi-tenant RAG**: Isolated document stores and vector search.
-   **Evaluations**: Built-in RAGAS/DeepEval integration.
-   **Security**: JWT auth, Rate limiting, and PII redaction.
-   **Observability**: Integrated MLflow, Prometheus, and Jaeger.
