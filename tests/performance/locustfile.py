"""
NeuroFlow Production Load Test

Usage:
    locust -f tests/performance/locustfile.py -H https://neuroflow-api.railway.app --headless -u 10 -r 2 --run-time 2m
"""

import os
import json
from locust import HttpUser, task, between, events


class NeuroFlowUser(HttpUser):
    """Simulates a typical NeuroFlow user performing health checks, queries, and evaluations."""

    wait_time = between(1, 3)
    token: str = ""

    def on_start(self) -> None:
        """Authenticate and obtain a JWT token before running tasks."""
        client_id = os.getenv("CLIENT_ID", "neuroflow-client")
        client_secret = os.getenv("CLIENT_SECRET", "neuroflow-secret")

        response = self.client.post(
            "/auth/token",
            json={"client_id": client_id, "client_secret": client_secret},
            name="/auth/token",
        )
        if response.status_code == 200:
            self.token = response.json().get("access_token", "")
        else:
            # Fallback: proceed without auth for endpoints that may not require it
            self.token = ""

    @property
    def auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    @task(5)
    def health_check(self) -> None:
        """High-frequency health check — lightweight, validates infrastructure."""
        self.client.get("/health", name="/health")

    @task(3)
    def query_rag(self) -> None:
        """Submit a RAG query — the core user action."""
        self.client.post(
            "/query",
            json={"query": "What are the key findings in the document?"},
            headers=self.auth_headers,
            name="/query",
        )

    @task(2)
    def list_evaluations(self) -> None:
        """Fetch evaluations — common dashboard action."""
        self.client.get(
            "/evaluations",
            headers=self.auth_headers,
            name="/evaluations",
        )

    @task(1)
    def get_metrics(self) -> None:
        """Scrape Prometheus metrics — simulates monitoring."""
        self.client.get("/metrics", name="/metrics")


@events.quitting.add_listener
def on_quitting(environment, **kwargs):  # type: ignore[no-untyped-def]
    """Print a summary when the test finishes."""
    stats = environment.stats
    print("\n" + "=" * 60)
    print("  NeuroFlow Load Test Summary")
    print("=" * 60)
    print(f"  Total Requests:      {stats.total.num_requests}")
    print(f"  Total Failures:      {stats.total.num_failures}")
    print(f"  Failure Rate:        {stats.total.fail_ratio:.2%}")
    print(f"  Avg Response Time:   {stats.total.avg_response_time:.0f}ms")
    print(f"  Median Response:     {stats.total.median_response_time}ms")
    print(f"  95th Percentile:     {stats.total.get_response_time_percentile(0.95):.0f}ms")
    print(f"  99th Percentile:     {stats.total.get_response_time_percentile(0.99):.0f}ms")
    print(f"  Req/s (avg):         {stats.total.total_rps:.1f}")
    print("=" * 60)
