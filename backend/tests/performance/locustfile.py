import random
import os
from locust import HttpUser, task, between, events
import json

SAMPLE_QUERIES = [
    "What is the transformer architecture?",
    "How does self-attention work?",
    "Explain the encoder-decoder structure.",
    "What are the benefits of multi-head attention?",
    "How is positional encoding used?"
]

TEST_DOCS = ["tests/fixtures/test_doc.pdf"]

class NeuroFlowUser(HttpUser):
    wait_time = between(1, 5)
    
    def on_start(self):
        # Login and get token
        response = self.client.post("/auth/token", json={
            "client_id": "neuroflow-client",
            "client_secret": "neuroflow-secret"
        })
        if response.status_code == 200:
            self.token = response.json()["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            self.token = None
            self.headers = {}

class QueryUser(NeuroFlowUser):
    weight = 7
    
    @task
    def query_pipeline(self):
        if not self.token: return
        # Using a dummy pipeline_id
        pipeline_id = "00000000-0000-0000-0000-000000000000"
        self.client.post("/query", json={
            "query": random.choice(SAMPLE_QUERIES),
            "pipeline_id": pipeline_id,
            "stream": False
        }, headers=self.headers)

class IngestUser(NeuroFlowUser):
    weight = 2
    
    @task
    def ingest_document(self):
        if not self.token: return
        file_path = random.choice(TEST_DOCS)
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                # Based on api/documents.py, it's /documents and field name is 'files'
                self.client.post("/documents", files={"files": f}, headers=self.headers)

class AdminUser(NeuroFlowUser):
    weight = 1
    
    @task
    def check_evaluations(self):
        if not self.token: return
        self.client.get("/evaluations/stream", headers=self.headers) # Usually it's a list, but we have stream
        # Or if there is a list endpoint we should use that. 
        # I'll check if /evaluations exists.
        self.client.get("/health", headers=self.headers)

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    # This would typically save results to a file if running in a real harness
    # But Locust handles summary reporting.
    pass
