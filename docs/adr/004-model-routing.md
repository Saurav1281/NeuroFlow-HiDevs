# ADR 004: Model Routing Strategy

## Context
NeuroFlow needs to serve varied query complexities, balancing cost, latency, and capability. Sending every query to GPT-4/Claude 3.5 Sonnet creates unsustainably high API costs and slow responses for simple tasks, while relying entirely on smaller/local models degrades quality for complex analytical queries.

## Decision
We will implement a **Dynamic Model Routing Matrix** within the Generation Subsystem. Queries are classified upon entry (using a fast, lightweight classifier or heuristic rules) and routed to one of three tiers:

### Routing Matrix

| Tier | Model Examples | Query Characteristics | Winning Scenario |
|---|---|---|---|
| **Tier 1 (Heavy)** | GPT-4 / Claude 3.5 Sonnet | Multi-hop reasoning, complex summarization, deep analytical questions, coding. | When precision and reasoning outweigh cost and latency. |
| **Tier 2 (General)** | GPT-4o-mini / Claude 3 Haiku | Standard Q&A, single-document retrieval, general entity extraction. | High-volume traffic requiring fast TTFT (time-to-first-token) at low cost. |
| **Tier 3 (Local/Fine-Tuned)** | Llama 3 8B (Fine-Tuned via NeuroFlow) | Specialized domain responses, internal taxonomy matching, strict format compliance. | Once fine-tuned on >1k high-quality logs, routes here for domain-specific mastery at zero API cost. |

## Consequences

**Positive:**
- Significant cost reduction by offloading simple queries to Tier 2 and Tier 3.
- Improves overall system latency for the majority of queries.
- Creates a clear ROI for the Fine-Tuning Subsystem: transitioning volume from Tier 1/2 down to Tier 3.

**Negative:**
- The router itself introduces slight latency upfront.
- Misclassification can result in poor answers (if routed too low) or wasted money (if routed too high). Continuous monitoring of routing accuracy is required.
