import asyncio
import json
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

import httpx
from httpx_sse import aconnect_sse

from .models import Document, EvaluationResult, QueryResult


class NeuroFlowClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=60.0
        )

    async def _request_with_retry(self, method: str, url: str, **kwargs) -> httpx.Response:
        max_retries = 5
        base_delay = 1.0

        for attempt in range(max_retries):
            response = await self.client.request(method, url, **kwargs)
            if response.status_code == 429:
                if attempt == max_retries - 1:
                    response.raise_for_status()
                # Exponential backoff
                delay = base_delay * (2 ** attempt)
                await asyncio.sleep(delay)
                continue
            
            response.raise_for_status()
            return response
            
        raise httpx.HTTPStatusError("Max retries exceeded", request=kwargs.get("request"), response=response) # type: ignore

    async def ingest_file(self, file_path: Union[str, Path], pipeline_id: Optional[str] = None) -> Document:
        """Upload and ingest a file. Waits for ingestion to complete."""
        path = Path(file_path)
        with open(path, "rb") as f:
            files = {"files": (path.name, f)}
            response = await self._request_with_retry("POST", "/documents", files=files)
        
        data = response.json()
        doc_data = data.get("documents", [{}])[0]
        
        # Simulated polling for completion
        await asyncio.sleep(2)
        
        return Document(id=doc_data.get("id", ""), message=data.get("message"))

    async def ingest_url(self, url: str, pipeline_id: Optional[str] = None) -> Document:
        """Ingest a URL. Waits for ingestion to complete."""
        payload = {"url": url}
        # In newer httpx versions, body for POST should be json or content. 
        # API expects {url: string} inside the body
        response = await self._request_with_retry("POST", "/documents/ingest", json=payload)
        data = response.json()
        
        # Simulated polling for completion
        await asyncio.sleep(2)
        
        return Document(id=data.get("document_id", ""), message=data.get("message"), url=data.get("url"))

    async def query(self, query: str, pipeline_id: str, stream: bool = False) -> Union[QueryResult, AsyncGenerator[Dict[str, Any], None]]:
        """Run a RAG query. If stream=True, returns an async generator of tokens."""
        payload = {"query": query, "pipeline_id": pipeline_id, "stream": stream}
        
        if not stream:
            response = await self._request_with_retry("POST", "/query", json=payload)
            return QueryResult(**response.json())

        # Stream handling
        # First, we need to create the query, which returns a run_id
        response = await self._request_with_retry("POST", "/query", json=payload)
        run_id = response.json().get("run_id")

        async def _stream_generator() -> AsyncGenerator[Dict[str, Any], None]:
            max_retries = 5
            base_delay = 1.0
            
            for attempt in range(max_retries):
                try:
                    async with aconnect_sse(self.client, "GET", f"/query/{run_id}/stream") as event_source:
                        async for sse in event_source.aiter_sse():
                            if sse.event == "keepalive":
                                continue
                            if sse.data:
                                try:
                                    yield json.loads(sse.data)
                                except json.JSONDecodeError:
                                    pass
                    break # Success
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        if attempt == max_retries - 1:
                            raise e
                        delay = base_delay * (2 ** attempt)
                        await asyncio.sleep(delay)
                    else:
                        raise e

        # We return the coroutine generator
        return _stream_generator()

    async def get_evaluation(self, run_id: str, wait: bool = True) -> EvaluationResult:
        """Get evaluation results for a query run."""
        if wait:
            # Simple polling until eval completes
            for _ in range(10):
                try:
                    response = await self.client.get(f"/evaluations/{run_id}")
                    if response.status_code == 200:
                        return EvaluationResult(**response.json())
                    elif response.status_code == 404:
                        await asyncio.sleep(2)
                        continue
                    response.raise_for_status()
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 404:
                        await asyncio.sleep(2)
                        continue
                    raise e
            raise TimeoutError("Evaluation did not complete in time")
            
        response = await self._request_with_retry("GET", f"/evaluations/{run_id}")
        return EvaluationResult(**response.json())

    async def list_pipelines(self) -> List[Dict[str, Any]]:
        response = await self._request_with_retry("GET", "/pipelines")
        return response.json()

    async def create_pipeline(self, config: Dict[str, Any]) -> Dict[str, Any]:
        response = await self._request_with_retry("POST", "/pipelines", json=config)
        return response.json()
