import time, requests

def main():
    print("Starting ingestion...")
    res = requests.post('http://localhost:8000/ingest', json={'repo_url': 'https://github.com/pallets/flask', 'force_reindex': True})
    print('Started:', res.json())
    job_id = res.json().get('job_id')
    if not job_id:
        return
        
    while True:
        status_res = requests.get(f'http://localhost:8000/status/{job_id}')
        status = status_res.json()
        print(status)
        if status.get('status') in ('ready', 'failed'):
            break
        time.sleep(2)

if __name__ == "__main__":
    main()
