import asyncio
import itertools
import json
import logging
import random
import time
from typing import Dict, Any, List

# Try to import mlflow for experiment tracking
try:
    import mlflow
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False

class HyperparamSearch:
    """Automated hyperparameter search for NeuroFlow retrieval tuning."""
    
    def __init__(self):
        self.param_grid = {
            "dense_k": [20, 40],
            "sparse_k": [10, 20],
            "rrf_k": [60, 120],
            "ef_search": [100, 200],
            "dense_weight": [0.6, 0.8]
        }
        self.experiment_name = "retrieval_optimization"
        
        if MLFLOW_AVAILABLE:
            try:
                mlflow.set_experiment(self.experiment_name)
            except Exception as e:
                print(f"MLflow setup failed: {e}. Logging to files only.")

    async def run_search(self, num_samples: int = 10, use_mock: bool = True):
        # Generate all combinations
        keys, values = zip(*self.param_grid.items())
        combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]
        
        # Sample if too many
        if len(combinations) > num_samples:
            combinations = random.sample(combinations, num_samples)
            
        print(f"Starting hyperparameter search across {len(combinations)} combinations...")
        
        best_mrr = 0.0
        best_config = None
        all_results = []
        
        for i, config in enumerate(combinations):
            print(f"[{i+1}/{len(combinations)}] Testing config: {config}")
            
            run_name = f"run_{int(time.time())}_{i}"
            
            # Start MLflow run
            if MLFLOW_AVAILABLE:
                with mlflow.start_run(run_name=run_name):
                    mlflow.log_params(config)
                    
                    # Simulate/Execute benchmark
                    results = await self._run_mock_benchmark(config)
                    
                    mlflow.log_metrics({
                        "hit_rate": results["hit_rate"],
                        "mrr": results["mrr"],
                        "latency_ms": results["latency_ms"]
                    })
            else:
                results = await self._run_mock_benchmark(config)
                
            all_results.append({
                "config": config,
                "metrics": results
            })
            
            if results["mrr"] > best_mrr:
                best_mrr = results["mrr"]
                best_config = config
                
        print(f"\nSearch complete. Best MRR: {best_mrr}")
        print(f"Best Config: {best_config}")
        
        # Save results
        with open("evaluation/hyperparam_search_results.json", "w") as f:
            json.dump({
                "best_config": best_config,
                "best_mrr": best_mrr,
                "all_runs": all_results
            }, f, indent=2)
            
        return best_config

    async def _run_mock_benchmark(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Simulates a benchmark run with the given config."""
        await asyncio.sleep(random.uniform(0.1, 0.3))
        
        # Heuristic: higher ef_search and rrf_k usually improve quality but increase latency
        base_hr = 0.80
        base_mrr = 0.60
        
        hr_boost = (config["ef_search"] - 100) / 1000 + (config["rrf_k"] - 60) / 1000
        mrr_boost = (config["ef_search"] - 100) / 2000 + (config["rrf_k"] - 60) / 500
        
        latency = 150 + (config["dense_k"] * 2) + (config["ef_search"] / 2)
        
        return {
            "hit_rate": round(min(0.98, base_hr + hr_boost + random.uniform(-0.02, 0.05)), 3),
            "mrr": round(min(0.85, base_mrr + mrr_boost + random.uniform(-0.01, 0.04)), 3),
            "latency_ms": round(latency + random.uniform(-10, 30), 2)
        }

if __name__ == "__main__":
    search = HyperparamSearch()
    asyncio.run(search.run_search(num_samples=12))
