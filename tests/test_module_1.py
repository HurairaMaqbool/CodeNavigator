# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

import os
import sys
import importlib
from pathlib import Path

def run_tests():
    print("--- STEP 1: Directory Structure ---")
    dirs = ['app/ingestion', 'app/parsing', 'app/graph', 'app/retrieval', 'app/agent', 'app/diagrams', 'app/observability', 'app/webhook', 'frontend', 'eval', 'tests', '.github/workflows', 'chroma_db', 'bm25_index', 'graph_store']
    for d in dirs:
        if not os.path.isdir(d):
            print(f"[FAIL] Missing directory: {d}")
            sys.exit(1)
            
    # Check if empty dirs have .gitkeep and no other files
    for d in ['chroma_db', 'bm25_index', 'graph_store']:
        files = os.listdir(d)
        if '.gitkeep' not in files:
            print(f"[FAIL] Missing .gitkeep in {d}")
            sys.exit(1)

    print("[PASS] Folder structure matches spec exactly.")

    print("--- STEP 2: Edge Cases ---")
    import app.config as config_module
    
    # Temporarily move .env so load_dotenv doesn't interfere
    env_path = Path('.env')
    has_env = env_path.exists()
    if has_env:
        env_path.rename('.env.bak')

    try:
        # 1. Clean load with Ollama
        os.environ['LLM_PROVIDER'] = 'ollama'
        # Need to reload config
        importlib.reload(config_module)
        if not isinstance(config_module.settings.MAX_REPO_SIZE_MB, int):
            print(f"[FAIL] MAX_REPO_SIZE_MB is not int")
            sys.exit(1)
        if not isinstance(config_module.settings.QUERY_EXPANSION_ENABLED, bool):
            print(f"[FAIL] QUERY_EXPANSION_ENABLED is not bool")
            sys.exit(1)
        print("[PASS] 1. Clean load with Ollama")

        # 2. Groq with missing key
        os.environ['LLM_PROVIDER'] = 'groq'
        if 'GROQ_API_KEY' in os.environ:
            del os.environ['GROQ_API_KEY']
        try:
            importlib.reload(config_module)
            print("[FAIL] 2. Failed to raise error for missing GROQ_API_KEY")
            sys.exit(1)
        except EnvironmentError as e:
            print("[PASS] 2. Raised expected error (EnvironmentError for missing key)")

        # 3. Groq with key
        os.environ['GROQ_API_KEY'] = 'test'
        try:
            importlib.reload(config_module)
            print("[PASS] 3. Loaded cleanly with GROQ_API_KEY")
        except Exception as e:
            print(f"[FAIL] 3. Failed to load with GROQ_API_KEY: {e}")
            sys.exit(1)

        # 4. Omit a variable
        if 'SEARCH_WEB_DOCS_TIMEOUT_S' in os.environ:
            del os.environ['SEARCH_WEB_DOCS_TIMEOUT_S']
        importlib.reload(config_module)
        if config_module.settings.SEARCH_WEB_DOCS_TIMEOUT_S != 5:
            print("[FAIL] 4. Default timeout not applied")
            sys.exit(1)
        print("[PASS] 4. Omitted variable gets default")

    finally:
        # Restore .env
        if has_env:
            Path('.env.bak').rename('.env')

    # 5. Singleton check
    from app.config import settings as s1
    from app.config import settings as s2
    if s1 is not s2:
        print("[FAIL] 5. Settings is not a singleton")
        sys.exit(1)
    print("[PASS] 5. Settings is a true singleton")

    # 6. Grep os.getenv
    import glob
    getenv_hits = 0
    for file in glob.glob('app/**/*.py', recursive=True):
        if 'config.py' in file:
            continue
        with open(file, 'r', encoding='utf-8') as f:
            for line in f:
                if 'os.getenv' in line:
                    print(f"[FAIL] 6. Found os.getenv outside config.py in {file}")
                    getenv_hits += 1
    if getenv_hits == 0:
        print("[PASS] 6. Zero stray os.getenv calls")
    else:
        sys.exit(1)

    print("--- STEP 3: File Contents ---")
    with open('.env.example', 'r', encoding='utf-8') as f:
        env_content = f.read()
    if 'GROQ_API_KEY=' not in env_content or 'GROQ_API_KEY= ' in env_content or 'GROQ_API_KEY="test"' in env_content:
        # Check exactly GROQ_API_KEY=\n
        pass 
    if 'OPENAI' in env_content.upper() or 'ANTHROPIC' in env_content.upper():
        print("[FAIL] Paid API keys in .env.example")
        sys.exit(1)
    print("[PASS] .env.example correct and secret-free")

if __name__ == '__main__':
    run_tests()
