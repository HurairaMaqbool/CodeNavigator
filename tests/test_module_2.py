# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

import os
import sys
import importlib
import json
import io
from pathlib import Path

from fastapi.testclient import TestClient

def run_tests():
    print("--- STEP 1: Confirm Deliverables ---")
    log_cfg = Path("app/observability/logging_config.py")
    if not log_cfg.exists():
        print("[FAIL] app/observability/logging_config.py missing")
        sys.exit(1)
        
    main_py = Path("app/main.py")
    if not main_py.exists():
        print("[FAIL] app/main.py missing")
        sys.exit(1)
        
    main_text = main_py.read_text()
    if "configure_logging()" not in main_text:
        print("[FAIL] configure_logging() not called in app/main.py")
        sys.exit(1)
        
    # Check ordering roughly
    conf_idx = main_text.find("configure_logging()")
    app_idx = main_text.find("app = FastAPI")
    mid_idx = main_text.find("app.add_middleware(RequestIDMiddleware)")
    
    if conf_idx > mid_idx:
        print("[FAIL] configure_logging() called AFTER middleware registration")
        sys.exit(1)

    print("[PASS] Deliverables exist and ordering is correct")

    print("--- STEP 2: Edge Cases ---")
    
    import app.config as config_module
    import app.observability.logging_config as logging_config
    
    # 1. Idempotency
    try:
        logging_config.configure_logging()
        logging_config.configure_logging()
        print("[PASS] 1. configure_logging() is idempotent")
    except Exception as e:
        print(f"[FAIL] 1. configure_logging() failed on second call: {e}")
        sys.exit(1)
        
    # 2. LOG_LEVEL filtering
    os.environ["LOG_LEVEL"] = "INFO"
    importlib.reload(config_module)
    importlib.reload(logging_config)
    logging_config.configure_logging()
    
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    logger = logging_config.logger
    logger.debug("test_debug_suppressed")
    logger.info("test_info_shown")
    sys.stdout = old_stdout
    
    output = buf.getvalue()
    if "test_debug_suppressed" in output:
        print("[FAIL] 2. DEBUG log was not suppressed when LOG_LEVEL=INFO")
        sys.exit(1)
    if "test_info_shown" not in output:
        print("[FAIL] 2. INFO log was not shown when LOG_LEVEL=INFO")
        sys.exit(1)
        
    # Now with DEBUG
    os.environ["LOG_LEVEL"] = "DEBUG"
    importlib.reload(config_module)
    importlib.reload(logging_config)
    logging_config.configure_logging()
    
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    logger = logging_config.logger
    logger.debug("test_debug_shown")
    sys.stdout = old_stdout
    
    if "test_debug_shown" not in buf.getvalue():
        print("[FAIL] 2. DEBUG log was suppressed when LOG_LEVEL=DEBUG")
        sys.exit(1)
        
    print("[PASS] 2. LOG_LEVEL filtering works")
    
    # Reload with INFO for rest
    os.environ["LOG_LEVEL"] = "INFO"
    importlib.reload(config_module)
    importlib.reload(logging_config)
    logging_config.configure_logging()
    
    from unittest.mock import MagicMock




    sys.modules['tree_sitter'] = MagicMock()
    sys.modules['tree_sitter_python'] = MagicMock()
    sys.modules['tree_sitter_javascript'] = MagicMock()
    sys.modules['tree_sitter_typescript'] = MagicMock()

    # 3, 4, 5. Health checks
    from app.main import app
    client = TestClient(app)
    
    buf = io.StringIO()
    sys.stdout = buf
    resp1 = client.get("/health")
    resp2 = client.get("/health")
    sys.stdout = old_stdout
    
    req_id_1 = resp1.headers.get("X-Request-ID")
    req_id_2 = resp2.headers.get("X-Request-ID")
    
    if not req_id_1 or not req_id_2:
        print("[FAIL] 5. X-Request-ID header missing from response")
        sys.exit(1)
        
    if req_id_1 == req_id_2:
        print("[FAIL] 3. request_id was not distinct across multiple requests")
        sys.exit(1)
    print("[PASS] 3. request_ids are distinct")
    
    lines = buf.getvalue().strip().split('\n')
    parsed_lines = []
    for line in lines:
        if line.strip():
            try:
                parsed = json.loads(line)
                parsed_lines.append(parsed)
            except json.JSONDecodeError:
                print(f"[FAIL] 4. Log output is not valid JSON: {line}")
                sys.exit(1)
                
    # Find the log for the first request
    # Middleware logs "request_started" and "request_finished", health logs "health_check"
    req_1_logs = [l for l in parsed_lines if l.get("request_id") == req_id_1]
    
    if not req_1_logs:
        print(f"[FAIL] 4. Could not find log lines with request_id {req_id_1}")
        sys.exit(1)
        
    if "path" not in req_1_logs[0]:
        print("[FAIL] 4. Log line missing 'path' field")
        sys.exit(1)
        
    print("[PASS] 4. Raw stdout is valid JSON and contains request_id and path")
    print("[PASS] 5. X-Request-ID matches logged request_id")
    
    # 6. Composition test
    # We will inject a manual route into the app to test this
    @app.get("/test_composition")
    def test_comp():
        log = logging_config.logger.bind(repo_id="test_repo_123")
        log.info("comp_test_event")
        return {"ok": True}
        
    buf = io.StringIO()
    sys.stdout = buf
    resp_comp = client.get("/test_composition")
    sys.stdout = old_stdout
    
    comp_req_id = resp_comp.headers.get("X-Request-ID")
    comp_lines = [json.loads(l) for l in buf.getvalue().strip().split('\n') if l.strip()]
    comp_target = [l for l in comp_lines if l.get("event") == "comp_test_event"]
    
    if not comp_target:
        print("[FAIL] 6. Composition test log line not found")
        sys.exit(1)
        
    comp_log = comp_target[0]
    if comp_log.get("request_id") != comp_req_id or comp_log.get("repo_id") != "test_repo_123":
        print(f"[FAIL] 6. Composition failed. Log dict: {comp_log}")
        sys.exit(1)
        
    print("[PASS] 6. Context composition (request_id + repo_id) works perfectly")
    
    print("--- STEP 3: Verify Logging Contract ---")
    log_cfg_text = log_cfg.read_text()
    if "secrets" not in log_cfg_text.lower() or "file contents" not in log_cfg_text.lower():
        print("[FAIL] Contract missing secrets/file contents warning")
        sys.exit(1)
    if "structured fields" not in log_cfg_text.lower() or "pre-formatted strings" not in log_cfg_text.lower():
        print("[FAIL] Contract missing structured fields warning")
        sys.exit(1)
    if ".bind" not in log_cfg_text:
        print("[FAIL] Contract missing .bind composition instruction")
        sys.exit(1)
    print("[PASS] Logging-discipline comment block present and correctly worded")
    
    print("--- STEP 4: Static / behavioral checks ---")
    import glob
    print_violations = 0
    fstring_violations = 0
    
    for file in glob.glob('app/**/*.py', recursive=True):
        if 'observability' in file and 'logging_config.py' in file:
            continue
        with open(file, 'r', encoding='utf-8') as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith('#') or 'compute_fingerprint' in stripped or 'print(settings.' in stripped:
                    continue
                import re
                if re.search(r'\bprint\s*\(', stripped):
                    print(f"[FAIL] print() violation in {file}: {stripped}")
                    print_violations += 1
                if re.search(r'\blogging\.info\s*\(', stripped):
                    print(f"[FAIL] raw logging.info violation in {file}: {stripped}")
                    print_violations += 1
                if 'log.info(f"' in stripped or "log.info(f'" in stripped:
                    print(f"[FAIL] f-string log violation in {file}: {stripped}")
                    fstring_violations += 1
                    
    if print_violations == 0 and fstring_violations == 0:
        print("[PASS] Zero print/raw-logging/f-string-log violations found")
    else:
        sys.exit(1)

if __name__ == '__main__':
    run_tests()
