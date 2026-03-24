# ADR 003: Evaluation Framework

## Context
NeuroFlow requires thousands of generation outputs to be rigorously scored to feed the Fine-Tuning Subsystem. Relying exclusively on human annotators for relevance, faithfulness, and precision is financially prohibitive, slow, and non-scalable, stalling the continuous improvement loop.

## Decision
We will utilize an **Automated LLM-as-Judge Evaluation Framework** (e.g., Ragas or TruLens) running asynchronously via message queues. 

1. **Metrics Computed:**
   - **Faithfulness:** Are sentences in the generated answer supported by the retrieved context?
   - **Answer Relevance:** Does the answer directly address the original query?
   - **Context Precision:** Was the retrieved context actually useful?
   - **Context Recall:** Did the retrieval fetch all necessary information?
2. **Judge Model:** We will standardize on a highly capable model (e.g., GPT-4o) specifically prompting it to output JSON scoring criteria (0-1).

## Consequences

**Positive:**
- **Velocity:** Thousands of queries can be evaluated every hour, powering live dashboards.
- **Automation loop:** We can algorithmically filter data (Faithfulness > 0.8) for fine-tuning without human bottlenecks.
- **Consistency:** An LLM-as-judge has steady behavioral criteria compared to multiple subjective human annotators.

**Negative / Risk Mitigation:**
- **Failure Mode 1 (Cost):** Running GPT-4o for every evaluation is expensive. *Mitigation:* We will sample 20% of standard queries for evaluation, while evaluating 100% of failed/flagged interactions.
- **Failure Mode 2 (Judge Bias):** The evaluator might prefer verbosity or its own native style (self-preference bias). *Mitigation:* We will implement a monthly ground-truth calibration set (100 queries) scored by humans to measure the Pearson correlation against the LLM judge. If correlation drops below 0.85, prompts or judge models require adjustment.
