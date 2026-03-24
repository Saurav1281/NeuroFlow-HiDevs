# System Architecture

NeuroFlow is comprised of five primary subsystems designed to handle the complete lifecycle of a retrieval-augmented generation (RAG) system with continuous evaluation and automated fine-tuning capabilities.

## 1. Ingestion Subsystem

**Responsibility:** Accepts raw files of various formats (PDF, DOCX, images, CSV, web URLs), extracts the content using modality-specific parsers, chunks the extracted text, embeds the chunks using an embedding model, and writes the semantic vectors and metadata to the vector store.

**Data Flow:**

```mermaid
flowchart TD
    A[File Upload / Web URL] --> B{Modality Router}
    B -->|PDF/DOCX| C[Text Extractor]
    B -->|Images| D[OCR Service]
    B -->|CSV/Tabular| E[Tabular Parser]
    B -->|URL| F[Web Scraper]
    
    C --> G[Chunking Engine]
    D --> G
    E --> G
    F --> G
    
    G --> H[Embedding Model]
    H --> I[(Vector Store - pgvector)]
    H --> J[(Document Store / Blob)]
```

## 2. Retrieval Subsystem

**Responsibility:** Receives a user query and executes parallel retrieval strategies. It performs embedding similarity search, keyword search (BM25), and metadata filtering. Results are fused, reranked, and formulated into a context window.

**Data Flow:**

```mermaid
flowchart TD
    Q[User Query] --> R1[Embedding & Vector Search]
    Q --> R2[Keyword/Lexical Search]
    Q --> R3[Metadata Filtering]
    
    R1 --> FUSE[Reciprocal Rank Fusion RRF]
    R2 --> FUSE
    R3 --> FUSE
    
    FUSE --> RERANK[Cross-Encoder Reranker]
    RERANK --> CONTEXT[Ranked Context Window]
```

## 3. Generation Subsystem

**Responsibility:** Takes the final context window and user query, formats them into a prompt template, and routes the request to the appropriate LLM based on cost tier, capability, or domain requirements. Responses are streamed token-by-token back to the user and full generation artifacts are logged.

**Data Flow:**

```mermaid
flowchart TD
    CW[Context Window] --> P[Prompt Assembler]
    UQ[User Query] --> P
    
    P --> ROUTER{Model Router}
    ROUTER -->|Tier 1 - Complex| M1[GPT-4/Claude-3.5-Sonnet]
    ROUTER -->|Tier 2 - General| M2[GPT-4o-mini/Claude-3-Haiku]
    ROUTER -->|Tier 3 - OSS/Local| M3[Llama 3 8B]
    
    M1 --> STREAM[SSE Stream to Client]
    M2 --> STREAM
    M3 --> STREAM
    
    STREAM -.-> LOG[(Evaluation Log Store)]
```

## 4. Evaluation Subsystem

**Responsibility:** Asynchronously evaluates generated responses against their retrieved contexts. It assigns scores for Faithfulness, Answer Relevance, Context Precision, and Context Recall. These scores power rolling aggregates and dashboards.

**Data Flow:**

```mermaid
flowchart TD
    LOG[(Evaluation Log Store)] --> Q1[Message Queue]
    Q1 --> EVAL[Automated LLM-as-Judge Evaluator]
    
    EVAL --> METRICS{Metrics Extractor}
    METRICS --> |Faithfulness > 0.8| FILTER[Quality Filter]
    METRICS --> |Answer Relevance| FILTER
    METRICS --> |Context Precision| AGG[Aggregator]
    METRICS --> |Context Recall| AGG
    
    FILTER --> PDB[(Postgres Scores DB)]
    AGG --> PDB
```

## 5. Fine-Tuning Subsystem

**Responsibility:** Extracts high-quality examples (based on strict evaluation thresholds) and prepares them for fine-tuning. Jobs are submitted, tracked via MLflow, and successfully fine-tuned models are registered for future intelligent routing.

**Data Flow:**

```mermaid
flowchart TD
    PDB[(Postgres Scores DB)] --> EXTRACT[High Quality Filter (Score > 0.8 & Rating >= 4)]
    EXTRACT --> FORMAT[JSONL Formatter]
    FORMAT --> FT_JOB[Fine-Tuning Job Handler]
    
    FT_JOB <--> MLflow[MLflow Tracker]
    FT_JOB --> REPO[Model Registry]
```
