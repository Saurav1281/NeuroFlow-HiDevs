# NeuroFlow Python SDK

A minimal and robust async Python SDK for the NeuroFlow developer API.

## Installation

```bash
pip install ./sdk
```

## Quickstart

```python
import asyncio
from neuroflow import NeuroFlowClient

async def main():
    # Initialize the client with auth token
    client = NeuroFlowClient(base_url="http://localhost:8000", api_key="admin-secret")
    
    # Ingest a document from a URL
    doc = await client.ingest_url("https://example.com/docs")
    print(f"Ingested document ID: {doc.id}")
    
    # Run a streaming query
    print("Response: ", end="", flush=True)
    pipeline_id = "00000000-0000-0000-0000-000000000000"  # Replace with actual
    
    async for token in await client.query("What is example.com?", pipeline_id=pipeline_id, stream=True):
        if token.get("type") == "token":
            print(token.get("delta", ""), end="", flush=True)
    print()

if __name__ == "__main__":
    asyncio.run(main())
```
