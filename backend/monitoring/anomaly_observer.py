import asyncio
import logging
import httpx
from typing import Set

logger = logging.getLogger("neuroflow.anomaly_observer")

class AnomalyObserver:
    """
    Polls Prometheus alerts and triggers the suggestions API when an anomaly is detected.
    """
    
    def __init__(self, prometheus_url: str = "http://prometheus:9090", api_url: str = "http://api:8000"):
        self.prometheus_url = prometheus_url
        self.api_url = api_url
        self.active_alerts: Set[str] = set() # Track active pipeline alert IDs to avoid spamming

    async def start(self):
        logger.info("AnomalyObserver started, monitoring for quality alerts...")
        while True:
            try:
                await self._check_alerts()
            except Exception as e:
                logger.error(f"Error checking alerts: {e}")
            await asyncio.sleep(60) # Poll every minute

    async def _check_alerts(self):
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.prometheus_url}/api/v1/alerts")
            if resp.status_code != 200:
                logger.warning(f"Failed to fetch alerts from Prometheus: {resp.status_code}")
                return

            data = resp.json()
            alerts = data.get("data", {}).get("alerts", [])
            
            # Filter for QualityAnomalyDetected alerts that are firing
            current_anomalies = []
            for alert in alerts:
                if alert.get("labels", {}).get("alertname") == "QualityAnomalyDetected" and alert.get("state") == "firing":
                    pipeline_id = alert.get("labels", {}).get("pipeline_id")
                    if pipeline_id:
                        current_anomalies.append(pipeline_id)

            # Trigger suggestions for newly firing anomalies
            for pipeline_id in current_anomalies:
                if pipeline_id not in self.active_alerts:
                    logger.info(f"Anomaly detected for pipeline {pipeline_id}. Triggering suggestions...")
                    try:
                        # Trigger suggestions API (POST will generate new suggestions)
                        await client.post(f"{self.api_url}/api/pipelines/{pipeline_id}/suggestions")
                        self.active_alerts.add(pipeline_id)
                    except Exception as e:
                        logger.error(f"Failed to trigger suggestions for {pipeline_id}: {e}")
            
            # Remove resolved alerts from tracking
            self.active_alerts = {pid for pid in self.active_alerts if pid in current_anomalies}
