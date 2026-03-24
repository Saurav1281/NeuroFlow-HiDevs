# ADR 002: Chunking Strategy

## Context
The Ingestion Subsystem needs to break down uploaded documents into smaller text segments (chunks). The resulting embeddings must capture the semantic meaning accurately while staying within context window limits. We evaluated fixed-size chunking, sentence-boundary chunking, and semantic chunking.

## Decision
We will employ a **hybrid chunking strategy** depending on the modality and structure of the input document:

1. **Default (Sentence-Boundary with Overlap):** 
   For standard unstructured text (PDFs, Word docs), we will use sentence-aware chunking (e.g., recursive character splitting via LangChain or LlamaIndex) with a target of 512 tokens and a 10% overlap (50 tokens). This respects grammatical boundaries and prevents context from being brutally severed mid-sentence.
2. **Semantic Chunking (Fallback for Complex Docs):** 
   For highly dense or technical documents, we will dynamically switch to semantic chunking (grouping text based on embedding similarities between sentences) to ensure cohesive paragraphs remain together, even if token thresholds vary.
3. **Structured Formats (CSV/JSON/Markdown):** 
   We will chunk at structural boundaries (e.g., row-level for CSVs, header-level for Markdown) instead of token counts.

## Consequences

**Positive:**
- Sentences are preserved, leading to cleaner retrieval and fewer "orphan" words that confuse the generation LLM.
- Adapts to the document structure, optimizing recall precision.

**Negative:**
- Higher ingestion latency and compute cost, since semantic chunking requires active embedding calls *during* the separation phase.
- Complexity in the Ingestion Subsystem to route documents to the correct chunking algorithms dynamically.
