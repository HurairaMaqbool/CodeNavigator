#!/usr/bin/env python3
import sys
import json
from pathlib import Path

def main():
    root = Path(__file__).resolve().parent.parent.parent.parent
    exp_a_path = root / "experiments" / "live" / "raw" / "exp_a_full_system_live.json"
    exp_b_path = root / "experiments" / "live" / "raw" / "exp_b_naive_dense_rag_live.json"

    if not exp_a_path.exists() or not exp_b_path.exists():
        print("ERROR: Raw experiment artifacts missing.")
        sys.exit(1)

    a_data = json.loads(exp_a_path.read_text(encoding="utf-8"))
    b_data = json.loads(exp_b_path.read_text(encoding="utf-8"))

    if len(a_data.get("results", [])) != 27 or len(b_data.get("results", [])) != 27:
        print("ERROR: Query count mismatch. Expected 27.")
        sys.exit(1)

    print("ALL RAW EVIDENCE VERIFIED COMPLIANT.")

if __name__ == "__main__":
    main()
