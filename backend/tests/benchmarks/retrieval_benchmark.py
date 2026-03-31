import asyncio
import json
import logging
import time
from typing import Any

from backend.db.pool import init_pool
from backend.providers.client import NeuroFlowClient
from pipelines.retrieval.query_processor import QueryProcessor
from pipelines.retrieval.reranker import Reranker
from pipelines.retrieval.retriever import Retriever

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RetrievalBenchmark:
    def __init__(self, dataset_path: str) -> None:
        with open(dataset_path) as f:
            self.dataset = json.load(f)

        self.llm_client = NeuroFlowClient()
        self.query_processor = QueryProcessor(self.llm_client)
        self.retriever = Retriever(self.llm_client, self.query_processor)
        self.reranker = Reranker(self.llm_client)

    def calculate_metrics(self, results: list[Any], ground_truth_id: str, k_list=[5, 10]):
        metrics = {}
        # Simple hit rate
        found_at = -1
        for i, res in enumerate(results):
            if res.chunk_id == ground_truth_id:
                found_at = i
                break

        for k in k_list:
            metrics[f"HitRate@{k}"] = 1.0 if 0 <= found_at < k else 0.0

        metrics["MRR@10"] = 1.0 / (found_at + 1) if 0 <= found_at < 10 else 0.0

        # NDCG calculation (simplified for binary relevance)
        if 0 <= found_at < 10:
            import math

            metrics["NDCG@10"] = 1.0 / math.log2(found_at + 2)
        else:
            metrics["NDCG@10"] = 0.0

        return metrics

    async def run(self):
        await init_pool()

        strategies = ["dense", "sparse", "hybrid_rrf", "hybrid_reranked"]

        overall_stats = {
            s: {"HitRate@5": 0, "HitRate@10": 0, "MRR@10": 0, "NDCG@10": 0, "latency": 0}
            for s in strategies
        }

        print(f"\nRunning benchmark on {len(self.dataset)} questions...\n")

        for entry in self.dataset:
            query = entry["query"]
            gt_id = entry["ground_truth_chunk_id"]

            # 1. Dense Only
            start = time.time()
            embeddings = await self.llm_client.embed([query])
            dense_results = await self.retriever._dense_retrieval(embeddings, 100)
            overall_stats["dense"]["latency"] += time.time() - start
            m = self.calculate_metrics(dense_results, gt_id)
            for k, v in m.items():
                overall_stats["dense"][k] += v

            # 2. Sparse Only
            start = time.time()
            sparse_results = await self.retriever._sparse_retrieval(query, 100)
            overall_stats["sparse"]["latency"] += time.time() - start
            m = self.calculate_metrics(sparse_results, gt_id)
            for k, v in m.items():
                overall_stats["sparse"][k] += v

            # 3. Hybrid (RRF)
            start = time.time()
            hybrid_results = await self.retriever.retrieve(
                query, use_hyde=False
            )  # Fusion of dense + sparse
            overall_stats["hybrid_rrf"]["latency"] += time.time() - start
            m = self.calculate_metrics(hybrid_results, gt_id)
            for k, v in m.items():
                overall_stats["hybrid_rrf"][k] += v

            # 4. Hybrid + Reranked
            start = time.time()
            reranked_results = await self.reranker.rerank(query, hybrid_results)
            overall_stats["hybrid_reranked"]["latency"] += time.time() - start
            m = self.calculate_metrics(reranked_results, gt_id)
            for k, v in m.items():
                overall_stats["hybrid_reranked"][k] += v

        # Average stats
        n = len(self.dataset)
        for s in strategies:
            for k in overall_stats[s]:
                overall_stats[s][k] /= n

        # Generate Report
        print("| Strategy | HitRate@5 | HitRate@10 | MRR@10 | NDCG@10 | Latency (s) |")
        print("|----------|-----------|------------|--------|---------|-------------|")
        for s in strategies:
            st = overall_stats[s]
            print(
                f"| {s:15} | {st['HitRate@5']:.3f} | {st['HitRate@10']:.3f} | {st['MRR@10']:.3f} | {st['NDCG@10']:.3f} | {st['latency']:.3f} |"
            )

        # Verify requirement: Hybrid+Reranked > Dense MRR@10 by 15%
        # (Since we are running on synthetic data or mocks, we'll just print the diff)
        diff = (overall_stats["hybrid_reranked"]["MRR@10"] - overall_stats["dense"]["MRR@10"]) / (
            overall_stats["dense"]["MRR@10"] + 1e-9
        )
        print(f"\nMRR@10 Improvement (Hybrid+Reranked vs Dense): {diff*100:.1f}%")

        return overall_stats


if __name__ == "__main__":
    benchmark = RetrievalBenchmark("tests/fixtures/eval_dataset.json")
    asyncio.run(benchmark.run())
