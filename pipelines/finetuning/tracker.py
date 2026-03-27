import mlflow
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class FineTuningTracker:
    """Tracks fine-tuning experiments using MLflow."""
    
    def __init__(self, experiment_name: str = "neuroflow_finetuning"):
        self.experiment_name = experiment_name
        try:
            mlflow.set_experiment(self.experiment_name)
        except Exception as e:
            logger.warning(f"MLflow experiment setup failed: {e}. Logging locally only.")

    def log_job_start(self, config: Dict[str, Any], training_file_id: str) -> str:
        """Starts a new MLflow run and logs initial configuration."""
        run = mlflow.start_run()
        mlflow.log_params(config)
        mlflow.log_param("training_file_id", training_file_id)
        logger.info(f"Started MLflow run: {run.info.run_id}")
        return run.info.run_id

    def log_job_metrics(self, run_id: str, metrics: Dict[str, float]):
        """Logs metrics during or after a fine-tuning job."""
        with mlflow.start_run(run_id=run_id, nested=True):
            mlflow.log_metrics(metrics)

    def log_job_complete(self, run_id: str, model_id: str, final_metrics: Dict[str, float]):
        """Logs completion status and final model ID."""
        with mlflow.start_run(run_id=run_id, nested=True):
            mlflow.log_param("fine_tuned_model", model_id)
            mlflow.log_metrics(final_metrics)
            mlflow.end_run()
        logger.info(f"Completed MLflow run: {run_id} with model: {model_id}")

    def log_artifact(self, run_id: str, local_path: str):
        """Logs local files (e.g., training data) as MLflow artifacts."""
        with mlflow.start_run(run_id=run_id, nested=True):
            mlflow.log_artifact(local_path)
