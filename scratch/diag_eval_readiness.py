from app.ingestion.repo_readiness import is_repo_ready
from eval.health_check import run_full_eval_precheck
from app.repo_resolver import resolve_asset_repo_id

JOB = "375c63667dff3e1e20ef5712cf1c0cb33940a9b49644bb855f1f89fe959d9f4d"
ASSET = "b4f947369301e4e0681a5f878604aa39c14efce4fbd98648e3722afd9f6380ee"

for label, rid in [("JOB", JOB), ("ASSET", ASSET), ("EMPTY", "")]:
    r = is_repo_ready(rid)
    pre = run_full_eval_precheck(rid, include_agent_probe=False)
    print(f"--- {label}")
    print(f"  repo_id={rid!r}")
    print(f"  ready={r.ready} pre_ok={pre.ok}")
    print(f"  sync_status={r.sync_status!r} files={r.files_parsed} chunks={r.chunks_created}")
    print(f"  asset_repo_id={r.asset_repo_id!r}")
    print(f"  block_reason={r.block_reason!r} block_message={r.block_message!r}")
    if not pre.ok:
        print(f"  pre_errors={pre.errors}")
    print()
