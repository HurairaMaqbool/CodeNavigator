import chromadb
from chromadb.config import Settings
import json

repo_id = "5749924cb6a9850057686b664b4b980fc407af109104df6f0a"
collection_name = repo_id + "_chunks"

chroma_client = chromadb.PersistentClient(path="./chroma_db", settings=Settings(anonymized_telemetry=False))
try:
    collection = chroma_client.get_collection(name=collection_name)
    count = collection.count()
    print(f"Total chunk count in Chroma for {collection_name}: {count}")
    
    results = collection.get(include=['metadatas'])
    metadatas = results.get('metadatas', [])
    paths = [m.get('file_path', '') for m in metadatas if m]
    
    contaminated = 0
    for p in set(paths):
        p_lower = p.lower()
        if "requests" in p_lower or "flask" in p_lower or "data/repos" in p_lower or "data\\repos" in p_lower:
            contaminated += 1
            
    print(f"Contaminated entries count: {contaminated}")
    
except Exception as e:
    print("Error querying Chroma:", e)

