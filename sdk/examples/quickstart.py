import asyncio
from neuroflow import NeuroFlowClient

async def main():
    print("Initializing client...")
    client = NeuroFlowClient(base_url="http://127.0.0.1:8000", api_key="admin-secret")
    
    print("\nIngesting document from URL...")
    try:
        doc = await client.ingest_url("https://neuroflow.dev/docs")
        print(f"Ingestion response ID: {doc.id}")
    except Exception as e:
        print(f"Ingestion failed: {e}")
        
    print("\nExecuting streaming RAG query...")
    print("Response: ", end="", flush=True)
    try:
        # We'll use a dummy pipeline ID
        pipeline_id = "00000000-0000-0000-0000-000000000000"
        async for token in await client.query("What is NeuroFlow?", pipeline_id=pipeline_id, stream=True):
            if token.get("type") == "token":
                print(token.get("delta", ""), end="", flush=True)
            elif token.get("type") == "done":
                print("\n[Done Streaming]")
        print()
    except Exception as e:
        print(f"\nQuery streaming failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
