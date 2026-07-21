import threading
import time
import random
from app.retrieval.bm25_store import query, upsert_chunks

def reader(repo_id: str):
    for i in range(10):
        try:
            res = query(repo_id, "test", top_k=5)
        except Exception as e:
            print(f"Reader error: {e}")
        time.sleep(random.random() * 0.01)

def writer(repo_id: str):
    for i in range(5):
        try:
            # Create a mock Document class compatible with upsert_chunks
            class MockDoc:
                def __init__(self, text, metadata):
                    self.page_content = text
                    self.metadata = metadata
            upsert_chunks(repo_id, [MockDoc(f"test text {i}", {"path": f"file{i}.py"})])
        except Exception as e:
            print(f"Writer error: {e}")
        time.sleep(random.random() * 0.02)

def main():
    repo_id = "test_concurrent_repo"
    threads = []
    
    for _ in range(5):
        t = threading.Thread(target=reader, args=(repo_id,))
        threads.append(t)
    for _ in range(2):
        t = threading.Thread(target=writer, args=(repo_id,))
        threads.append(t)
        
    for t in threads:
        t.start()
        
    for t in threads:
        t.join()
        
    print("Concurrency test completed. If no errors above, locks are working.")

if __name__ == '__main__':
    main()
