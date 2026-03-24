# ADR 001: Vector Store Selection

## Context
NeuroFlow requires a high-performance vector store to manage document embeddings, metadata filtering, and high-throughput retrieval operations. The system must support Reciprocal Rank Fusion (RRF), combining semantic and keyword searches. We considered standalone stores like Pinecone, Weaviate, and Qdrant, as well as relational extensions like pgvector (PostgreSQL).

## Decision
We will use **pgvector** hosted on PostgreSQL as our primary vector store and metadata database. 

1. **Colocation of Data:** pgvector allows storing embeddings alongside rich relational metadata without syncing issues between a relational DB and a separate vector DB.
2. **Hybrid Search:** It inherently supports exact keyword/lexical searches (via GIN indices/`tsvector`) combined seamlessly with semantic search (HNSW or IVFFlat indices) using standard SQL, making RRF implementation straightforward.
3. **Operational Simplicity:** Avoids managing a separate infrastructure component. Postgres is already required for the Evaluation Subsystem (storing scores) and Fine-Tuning logs.
4. **Cost:** Pinecone and others carry high managed-service costs at scale, whereas pgvector leverages our existing Postgres footprint.

## Consequences

**Positive:**
- Simplified infrastructure topology (one database system).
- ACID compliance across document metadata, vector embeddings, and evaluation scores.
- Zero data synchronization lag between document states and their vectors.

**Negative:**
- Performance at extreme scale (>100M vectors) might require careful tuning of HNSW indices compared to purpose-built engines like Qdrant.
- Compute scaling is tied to Postgres vertical scaling, rather than fully detached vector-compute limits.
