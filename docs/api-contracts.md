# API Contracts

All endpoints are prefixed with `/api/v1`.
All endpoints (except `/health` and `/metrics`) require authentication via a Bearer token in the `Authorization` header.
Default Rate Limit: 100 requests per minute per user/IP.

---

## POST /ingest
Accepts raw files or URLs for ingestion, extraction, chunking, and embedding.

- **HTTP Method:** `POST`
- **Path:** `/ingest`
- **Auth:** Required
- **Rate Limit:** 20 req/min
- **Request Body (JSON):**
  ```json
  {
    "source_type": "url",
    "url": "https://example.com/doc",
    "metadata": {
      "author": "Jane Doe",
      "category": "technical"
    }
  }
  ```
  *(For files, use `multipart/form-data` with a `file` field instead)*
- **Response Body (JSON):**
  ```json
  {
    "status": "success",
    "document_id": "doc_12345",
    "chunks_created": 42
  }
  ```
- **Error Codes:**
  - `400`: Invalid source type or missing payload
  - `415`: Unsupported media type
  - `429`: Rate limit exceeded

---

## POST /query
Executes the RAG query pipeline and returns an immediate response or a query ID for SSE streaming.

- **HTTP Method:** `POST`
- **Path:** `/query`
- **Auth:** Required
- **Rate Limit:** 60 req/min
- **Request Body (JSON):**
  ```json
  {
    "query": "What are the core components of NeuroFlow?",
    "stream": true,
    "filters": {
      "category": "technical"
    }
  }
  ```
- **Response Body (JSON):**
  *(If `stream: false`)*
  ```json
  {
    "query_id": "q_9876",
    "answer": "NeuroFlow consists of ingestion, retrieval...",
    "sources": ["doc_12345"]
  }
  ```
  *(If `stream: true`)*
  ```json
  {
    "query_id": "q_9876",
    "stream_url": "/api/v1/query/q_9876/stream"
  }
  ```
- **Error Codes:**
  - `400`: Empty query
  - `500`: Retrieval/Generation failure

---

## GET /query/{query_id}/stream
Provides an SSE stream consisting of generation tokens.

- **HTTP Method:** `GET`
- **Path:** `/query/{query_id}/stream`
- **Auth:** Required
- **Rate Limit:** 10 req/min (concurrent connections limit)
- **Response Body:**
  *Server-Sent Events (SSE) format emitting JSON strings.*
  ```text
  data: {"token": "Neuro"}
  data: {"token": "Flow "}
  data: {"done": true}
  ```
- **Error Codes:**
  - `404`: Query ID not found or expired

---

## GET /evaluations
Retrieves paginated evaluation logs and scores for previous generations.

- **HTTP Method:** `GET`
- **Path:** `/evaluations`
- **Auth:** Required
- **Rate Limit:** 60 req/min
- **Query Params:** `page` (int), `limit` (int)
- **Response Body (JSON):**
  ```json
  {
    "data": [
      {
        "evaluation_id": "eval_111",
        "query_id": "q_9876",
        "scores": {
          "faithfulness": 0.95,
          "answer_relevance": 0.92,
          "context_precision": 0.88,
          "context_recall": 0.85
        }
      }
    ],
    "pagination": { "page": 1, "total": 1500 }
  }
  ```

---

## GET /evaluations/aggregate
Provides aggregate metrics over a specified rolling window.

- **HTTP Method:** `GET`
- **Path:** `/evaluations/aggregate`
- **Auth:** Required
- **Rate Limit:** 60 req/min
- **Query Params:** `window` (e.g., `7d`, `30d`)
- **Response Body (JSON):**
  ```json
  {
    "window": "7d",
    "average_faithfulness": 0.92,
    "average_relevance": 0.89
  }
  ```

---

## POST /pipelines
Creates a named pipeline configuration (for defining chunking logic, models, or evaluation weights).

- **HTTP Method:** `POST`
- **Path:** `/pipelines`
- **Auth:** Required (Admin)
- **Rate Limit:** 20 req/min
- **Request Body (JSON):**
  ```json
  {
    "name": "standard-rag-v2",
    "config": {
      "chunk_size": 512,
      "embedding_model": "text-embedding-3-small"
    }
  }
  ```
- **Response Body (JSON):**
  ```json
  {
    "id": "pipe_333",
    "status": "created"
  }
  ```

---

## GET /pipelines/{id}/runs
Retrieves the execution history of a specific pipeline.

- **HTTP Method:** `GET`
- **Path:** `/pipelines/{id}/runs`
- **Auth:** Required
- **Rate Limit:** 60 req/min
- **Response Body (JSON):**
  ```json
  {
    "runs": [
      {
        "run_id": "run_444",
        "status": "completed",
        "duration_ms": 4500
      }
    ]
  }
  ```

---

## POST /finetune/jobs
Submits a dataset extraction and fine-tuning job.

- **HTTP Method:** `POST`
- **Path:** `/finetune/jobs`
- **Auth:** Required (Admin)
- **Rate Limit:** 5 req/min
- **Request Body (JSON):**
  ```json
  {
    "base_model": "llama-3-8b",
    "filter_criteria": {
      "min_faithfulness": 0.8,
      "min_user_rating": 4
    }
  }
  ```
- **Response Body (JSON):**
  ```json
  {
    "job_id": "ft_job_555",
    "status": "queued"
  }
  ```

---

## GET /finetune/jobs/{id}
Retrieves status and training metrics for a fine-tuning job.

- **HTTP Method:** `GET`
- **Path:** `/finetune/jobs/{id}`
- **Auth:** Required
- **Rate Limit:** 60 req/min
- **Response Body (JSON):**
  ```json
  {
    "job_id": "ft_job_555",
    "status": "training",
    "metrics": {
      "epoch": 2,
      "loss": 0.45
    }
  }
  ```

---

## GET /health
Basic system health check.

- **HTTP Method:** `GET`
- **Path:** `/health`
- **Auth:** None
- **Rate Limit:** 1000 req/min
- **Response Body (JSON):**
  ```json
  { "status": "ok", "uptime_seconds": 3600 }
  ```

---

## GET /metrics
Prometheus-compatible metrics endpoint.

- **HTTP Method:** `GET`
- **Path:** `/metrics`
- **Auth:** Internal/Infra only
- **Response Header:** `Content-Type: text/plain`
- **Response Body:** Standard Prometheus format payload.
