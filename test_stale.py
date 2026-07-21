import asyncio
from pathlib import Path
from app.ingestion.pipeline import ingest_repository
import chromadb

def get_chunk_count(repo_id):
    client = chromadb.PersistentClient(path='./chroma_db')
    try:
        c = client.get_collection(f"{repo_id}_chunks")
        return c.count()
    except Exception:
        return 0

async def main():
    repo_url = "dummy123"
    repo_id = "test_stale_purge_123"
    
    # First ingest
    await ingest_repository("d:/github project/codebase-onboarding-agent/app/api", repo_url, _force_repo_id=repo_id)
    print("First ingest count:", get_chunk_count(repo_id))
    
    # Second ingest
    await ingest_repository("d:/github project/codebase-onboarding-agent/app/api", repo_url, _force_repo_id=repo_id)
    print("Second ingest count:", get_chunk_count(repo_id))

if __name__ == '__main__':
    asyncio.run(main())
