# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
frontend/streamlit_app.py
-------------------------
Professional Streamlit UI for the CodeNavigator.
"""
from __future__ import annotations

import os
import time
import uuid
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import api_client
from ui_theme import (
    APP_VERSION,
    inject_styles,
    render_alert,
    render_backend_status,
    render_citation_chips,
    render_empty_chat,
    render_empty_stats,
    render_empty_workspace,
    render_footer,
    render_hero,
    render_ingest_stepper,
    render_ragas_chart,
    render_sidebar_nav,
    render_stat_card,
    render_top_header,
    section_header,
    status_pill_html,
)
from theme import apply_branding, render_theme_mode_toggle
from voice_output import render_voice_output_toggle

# ---------------------------------------------------------------------------
# Page config (must be first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="CodeNavigator",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_styles()  # Module #34 boot_theme() — dark default, CSS variables once

# Optional UI password gate (set STREAMLIT_UI_PASSWORD in env)
_ui_password = os.environ.get("STREAMLIT_UI_PASSWORD", "").strip()
if _ui_password and not st.session_state.get("ui_authenticated"):
    st.markdown("### Sign in")
    entered = st.text_input("Password", type="password", key="ui_password_input")
    if st.button("Continue", type="primary"):
        if entered == _ui_password:
            st.session_state.ui_authenticated = True
            st.rerun()
        else:
            st.error("Invalid password")
    st.stop()

# Session state
if "repo_id" not in st.session_state:
    st.session_state.repo_id = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "active_page" not in st.session_state:
    st.session_state.active_page = "Workspace"
if "voice_permission_denied" not in st.session_state:
    st.session_state.voice_permission_denied = False
if "last_diagram_symbol" not in st.session_state:
    st.session_state.last_diagram_symbol = None
if "voice_output_enabled" not in st.session_state:
    st.session_state.voice_output_enabled = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_api_error(e: api_client.APIError) -> tuple[str, str]:
    """Return (alert_level, message) for APIError."""
    if e.status_code == 409:
        return "info", "Repository is still indexing — try again shortly."
    if e.status_code == 429:
        wait = e.retry_after_s or 30
        return (
            "error",
            e.message
            or f"The AI provider is temporarily rate-limited. Please wait about {wait} seconds and try again.",
        )
    if e.status_code == 504:
        return (
            "error",
            e.message
            or "The request took too long. Try a simpler, more specific question.",
        )
    return "error", e.message


def _run_chat_exchange(question: str) -> None:
    """Shared typed + voice chat path — POST /chat with loading experience."""
    st.session_state.chat_history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        progress_slot = st.empty()
        skeleton_slot = st.empty()
        t0 = time.time()
        try:
            from loading_experience import run_chat_with_loading
            from voice_output import render_read_aloud_controls

            ans = run_chat_with_loading(
                progress_slot,
                skeleton_slot,
                session_id=st.session_state.session_id,
                repo_id=st.session_state.repo_id,
                question=question,
                chat_callable=api_client.chat,
            )
            progress_slot.empty()
            skeleton_slot.empty()
            elapsed = time.time() - t0
            text = ans.get("answer", "")
            gated = ans.get("gated", False)
            is_timeout = any(
                x in (text or "").lower()
                for x in ("timed out", "too slow", "rate-limited", "rate limit")
            )
            if gated and is_timeout:
                render_alert("error", text or "Request failed.", icon="⚠️")
            elif gated:
                render_alert("warning", text or "Could not verify citations.", icon="🛡️")
            else:
                st.markdown(text)
            if text and not gated:
                render_read_aloud_controls(text)
            st.caption(
                "⚡ Cached" if ans.get("cache_hit") else f"Completed in {elapsed:.1f}s"
            )
            if ans.get("sources"):
                with st.expander("▸ Sources", expanded=False):
                    render_citation_chips(ans["sources"])
            if ans.get("trace"):
                with st.expander("▸ Agent trace", expanded=False):
                    st.json(ans["trace"])
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": text,
                "gated": gated,
                "cache_hit": ans.get("cache_hit"),
                "sources": ans.get("sources"),
                "trace": ans.get("trace"),
            })
        except api_client.APIError as e:
            progress_slot.empty()
            skeleton_slot.empty()
            level, msg = _format_api_error(e)
            render_alert(level, msg)
        except Exception as e:
            progress_slot.empty()
            skeleton_slot.empty()
            import requests as _req
            if isinstance(e, (_req.exceptions.Timeout, _req.exceptions.ReadTimeout)):
                render_alert(
                    "error",
                    "Request timed out — try a simpler, more specific question.",
                )
            elif isinstance(e, _req.exceptions.ConnectionError):
                render_alert("error", "Cannot reach backend on port 8000.")
            else:
                render_alert("error", str(e))


def _run_diagram_for_symbol(symbol: str, depth: int = 2) -> None:
    """Shared diagram path for sidebar button and voice shortcut."""
    st.session_state.last_diagram_symbol = symbol.strip()
    with st.spinner("Building diagram…"):
        try:
            diag_res = api_client.get_diagram(
                st.session_state.repo_id, symbol.strip(), depth
            )
            mermaid_code = diag_res.get("mermaid")
            if not mermaid_code or str(mermaid_code).strip() in ("", "graph TD"):
                render_alert("info", "No graph found for this symbol.")
            else:
                if diag_res.get("clamped"):
                    st.caption("Depth clamped for readability.")
                render_mermaid(mermaid_code)
        except api_client.APIError as e:
            render_alert("error", e.message)


def render_mermaid(mermaid_code: str) -> None:
    try:
        from theme import apply_branding
    except ImportError:
        from frontend.theme import apply_branding

    open_tag = apply_branding("diagram")
    st.markdown(open_tag, unsafe_allow_html=True)
    mermaid_html = f"""
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <script>mermaid.initialize({{startOnLoad:true, theme:'neutral'}});</script>
    <div class="mermaid">{mermaid_code}</div>
    """
    components.html(mermaid_html, height=480, scrolling=True)
    st.markdown("</div>", unsafe_allow_html=True)


def display_status_badges(meta: dict[str, Any]) -> None:
    status = meta.get("sync_status", "unknown")
    st.markdown(status_pill_html(status), unsafe_allow_html=True)
    render_ingest_stepper(status)

    files = meta.get("files_parsed")
    chunks = meta.get("chunks_created")
    if status == "synced":
        cols = st.columns(2)
        render_stat_card("Files", str(files if files is not None else "—"), cols[0])
        render_stat_card("Chunks", str(chunks if chunks is not None else "—"), cols[1])
    elif status in ("pending", "indexing", "parsing", "filtering", "cloning"):
        render_empty_stats()
    elif status == "failed":
        render_alert("error", meta.get("error_reason") or "Ingestion failed.")

    if meta.get("graph_truncated"):
        render_alert("warning", "Graph truncated (size limit).")
    if meta.get("has_circular_dependencies") is True:
        st.caption("Import cycles detected (shown in diagrams)")


def render_per_question_diagnostics(
    run: dict[str, Any] | None,
    *,
    title: str = "Per-Question Diagnostics",
) -> None:
    if not run:
        return

    section_header(title)
    version = run.get("version") or run.get("timestamp") or "unknown"
    diag = run.get("diagnostics") or {}
    rows = diag.get("per_question") or []

    c1, c2, c3, c4 = st.columns(4)
    render_stat_card("Questions", str(diag.get("question_count", len(rows) or "—")), c1)
    render_stat_card("Gated", str(diag.get("gated_count", "—")), c2)
    render_stat_card("Mean P@3", f"{run.get('retrieval_precision_at_3', 0):.2f}", c3)
    render_stat_card("Version", str(version)[:14], c4)

    if not rows:
        st.info("Re-run evaluation to populate per-question diagnostics.")
        return

    table_rows = [
        {
            "#": i,
            "Hit": "✅" if row.get("gt_hit") else "❌",
            "P@3": row.get("precision_at_3", 0),
            "Gated": row.get("gated", False),
            "Conf": row.get("confidence_score", 0),
            "Question": (row.get("question") or "")[:90],
        }
        for i, row in enumerate(rows, 1)
    ]
    st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

    misses = [r for r in rows if not r.get("gt_hit")]
    if misses:
        with st.expander(f"Misses ({len(misses)})", expanded=False):
            for row in misses:
                st.markdown(f"**{(row.get('question') or '')[:120]}**")
                st.caption(
                    f"Top: {', '.join(row.get('top_files') or []) or '(none)'} · "
                    f"Expected: {', '.join(row.get('ground_truth_files') or [])}"
                )


def _poll_ingestion(job_id: str) -> dict[str, Any]:
    with st.status("Indexing repository…", expanded=True) as box:
        while True:
            status_res = api_client.get_status(job_id)
            curr = status_res.get("status")
            if curr == "ready":
                box.update(
                    label=f"Done — {status_res.get('files_parsed', '?')} files indexed",
                    state="complete",
                    expanded=False,
                )
                return status_res
            if curr == "failed":
                box.update(
                    label=f"Failed: {status_res.get('error_reason', 'unknown')}",
                    state="error",
                )
                return status_res
            box.update(label=f"Indexing… ({status_res.get('sync_status', 'pending')})")
            time.sleep(2)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
backend_ok = render_backend_status()

st.sidebar.divider()
render_theme_mode_toggle()
render_voice_output_toggle()

st.sidebar.divider()
page = render_sidebar_nav(st.session_state.get("active_page", "Workspace"))
st.session_state.active_page = page

if st.session_state.repo_id:
    st.sidebar.markdown("---")
    st.sidebar.caption("Active repository")
    short = st.session_state.repo_id
    st.sidebar.code((short[:22] + "…") if len(short) > 22 else short, language=None)
    if st.sidebar.button("Clear session", use_container_width=True, type="secondary"):
        st.session_state.repo_id = None
        st.session_state.chat_history = []
        st.session_state.session_id = str(uuid.uuid4())
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption("Quick start")
for label, url in [
    ("psf / requests", "https://github.com/psf/requests"),
    ("pallets / flask", "https://github.com/pallets/flask"),
]:
    if st.sidebar.button(label, key=f"quick_{label}", use_container_width=True):
        if backend_ok:
            try:
                res = api_client.ingest(url)
                st.session_state.repo_id = res["job_id"]
                _poll_ingestion(res["job_id"])
                st.rerun()
            except api_client.APIError as e:
                st.sidebar.error(str(e.message))
            except Exception as e:
                import requests as _req
                if isinstance(e, (_req.exceptions.Timeout, _req.exceptions.ReadTimeout)):
                    st.sidebar.warning("Ingest start timed out — check backend on :8000")
                else:
                    st.sidebar.error(str(e))
        else:
            st.sidebar.error("Start backend first")

# ---------------------------------------------------------------------------
# Main content
# ---------------------------------------------------------------------------
render_top_header(backend_ok)
render_hero()

if page == "Workspace":
    # --- Ingest ---
    st.markdown('<div class="ingest-panel">', unsafe_allow_html=True)
    section_header("Repository", "Paste a public GitHub URL — or use Quick start in the sidebar")
    with st.form("ingest_form", clear_on_submit=False):
        c1, c2, c3 = st.columns([4.2, 1.1, 1.1])
        with c1:
            repo_url = st.text_input(
                "GitHub URL",
                placeholder="https://github.com/owner/repo",
                label_visibility="collapsed",
            )
        with c2:
            ref = st.text_input("Branch", placeholder="main", label_visibility="collapsed")
        with c3:
            submitted = st.form_submit_button("Ingest", type="primary", use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    if submitted and repo_url:
        url_clean = repo_url.strip()
        if not url_clean.startswith("https://github.com"):
            render_alert("warning", "Enter a valid `https://github.com/...` URL")
        elif backend_ok:
            try:
                res = api_client.ingest(url_clean, ref or None)
                st.session_state.repo_id = res["job_id"]
                _poll_ingestion(res["job_id"])
                st.rerun()
            except api_client.APIError as e:
                level, msg = _format_api_error(e)
                render_alert(level, msg)
            except Exception as e:
                import requests as _req
                if isinstance(e, (_req.exceptions.Timeout, _req.exceptions.ReadTimeout)):
                    render_alert(
                        "error",
                        "Backend took too long to start ingest. "
                        "Ensure the API is running on port 8000 and Redis is up (or disabled). "
                        "Retry in a few seconds.",
                    )
                else:
                    render_alert("error", str(e))
        else:
            st.error("Backend is offline. Run: `python -m uvicorn app.main:app --port 8000`")

    if not st.session_state.repo_id:
        render_empty_workspace()
        render_footer()
        st.stop()

    try:
        meta = api_client.get_status(st.session_state.repo_id)
    except api_client.APIError:
        st.error("Could not load repository status.")
        meta = {}

    is_ready = meta.get("sync_status") == "synced"

    col_main, col_side = st.columns([2.2, 1])
    with col_side:
        st.markdown('<div class="cn-panel-card">', unsafe_allow_html=True)
        section_header("Status")
        display_status_badges(meta)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="cn-panel-card">', unsafe_allow_html=True)
        section_header("Call graph")
        diag_func = st.text_input("Symbol", placeholder="Session.send")
        diag_depth = st.slider("Depth", 1, 5, 2)
        if st.button("Generate diagram", use_container_width=True, type="secondary"):
            if not is_ready:
                render_alert("warning", "Wait until indexing completes.")
            elif not diag_func.strip():
                render_alert("info", "Enter a function or class name.")
            else:
                _run_diagram_for_symbol(diag_func.strip(), diag_depth)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_main:
        section_header("Chat")
        if not st.session_state.chat_history:
            render_empty_chat()

        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                content = msg.get("content") or ""
                gated = msg.get("gated", False)
                is_timeout = gated and any(
                    x in content.lower()
                    for x in ("timed out", "too slow", "rate-limited", "rate limit")
                )
                if gated and is_timeout:
                    render_alert("error", content or "Request failed.", icon="⚠️")
                elif gated:
                    render_alert("warning", content or "Could not verify citations.", icon="🛡️")
                else:
                    st.markdown(content)
                if msg.get("cache_hit"):
                    st.caption("⚡ Cache hit")
                if msg.get("sources"):
                    with st.expander("▸ Sources", expanded=False):
                        render_citation_chips(msg["sources"])
                if msg.get("trace"):
                    with st.expander("▸ Agent trace", expanded=False):
                        st.json(msg["trace"])

        from voice_input import (
            apply_browser_voice_event,
            drain_browser_voice_event,
            render_permission_notice,
            render_voice_input,
        )

        voice_browser_event = drain_browser_voice_event()
        pending_voice_action = None
        if voice_browser_event:
            pending_voice_action = apply_browser_voice_event(
                voice_browser_event,
                st.session_state.chat_history,
                last_diagram_symbol=st.session_state.last_diagram_symbol,
            )

        render_voice_input(disabled=not is_ready)
        render_permission_notice()

        question = st.chat_input(
            "Ask about architecture, data flow, or specific code…",
            disabled=not is_ready,
        )

        if pending_voice_action and pending_voice_action.get("route") == "diagram":
            _run_diagram_for_symbol(pending_voice_action["symbol"])

        chat_question = question
        if not chat_question and pending_voice_action:
            route = pending_voice_action.get("route")
            if route in ("chat", "explain_again"):
                chat_question = pending_voice_action.get("question")

        if chat_question:
            _run_chat_exchange(chat_question)

elif page == "Evaluation & QA":
    # --- Evaluation & QA ---
    section_header("Evaluation & quality assurance", "RAGAS metrics, version compare, golden-set CI")

    eval_ready = False
    eval_health: dict = {}
    if st.session_state.repo_id:
        try:
            eval_health = api_client.get_eval_health(st.session_state.repo_id, probe_agent=False)
            eval_ready = bool(eval_health.get("ok"))
            details = eval_health.get("details") or {}
            c1, c2, c3 = st.columns(3)
            render_stat_card(
                "Index",
                "Ready" if eval_ready else "Not ready",
                c1,
            )
            render_stat_card("Chunks", str(details.get("chroma_chunk_count", "—")), c2)
            render_stat_card("Probe hits", str(details.get("probe_hit_count", "—")), c3)
            if not eval_ready:
                for err in eval_health.get("errors") or []:
                    render_alert("error", str(err))
        except Exception as err:
            render_alert("error", f"Health check: {err}")
    else:
        st.info("Ingest a repo on the Workspace tab first.")

    st.markdown("<br>", unsafe_allow_html=True)
    btn_col1, btn_col2, _ = st.columns([1, 1, 2])
    run_disabled = not st.session_state.repo_id or not eval_ready
    with btn_col1:
        run_eval_clicked = st.button(
            "Run RAGAS eval",
            type="primary",
            disabled=run_disabled,
            use_container_width=True,
        )
    with btn_col2:
        run_golden_clicked = st.button(
            "Run Golden CI",
            disabled=not backend_ok,
            use_container_width=True,
        )

    if run_eval_clicked:
        try:
            job_info = api_client.start_eval(st.session_state.repo_id)
            job_id = job_info.get("job_id")
            if not job_id:
                st.error("No job_id returned from backend.")
            else:
                with st.status("RAGAS evaluation running…", expanded=True) as box:
                    progress = st.progress(0)
                    t0 = time.time()
                    eval_res = None
                    eval_error = None
                    while True:
                        elapsed = int(time.time() - t0)
                        progress.progress(min(0.95, elapsed / 1800))
                        try:
                            resp = api_client.get_eval_status(job_id)
                        except Exception as exc:
                            eval_error = str(exc)
                            break
                        job_status = resp.get("status")
                        if job_status == "done":
                            eval_res = resp.get("result")
                            progress.progress(1.0)
                            box.update(label="Evaluation complete", state="complete")
                            break
                        if job_status == "error":
                            eval_error = resp.get("error", "Unknown error")
                            box.update(label="Evaluation failed", state="error")
                            break
                        if elapsed > 1800:
                            eval_error = "Timed out after 30 minutes"
                            break
                        time.sleep(3)
                if eval_res:
                    section_header("RAGAS scores")
                    render_ragas_chart(eval_res.get("ragas_scores", {}))
                    if eval_res.get("regression_warning"):
                        st.warning("Regression vs prior run (same question count)")
                        with st.expander("Details"):
                            st.code(eval_res["regression_warning"])
                    else:
                        st.success("Evaluation saved successfully.")
                    supp = eval_res.get("supplementary", {})
                    if supp:
                        st.dataframe(pd.DataFrame([supp]), use_container_width=True, hide_index=True)
                    render_per_question_diagnostics(eval_res)
                elif eval_error:
                    st.error(eval_error)
        except api_client.APIError as e:
            st.error(e.message)

    if run_golden_clicked:
        try:
            job = api_client.start_golden_run()
            job_id = job.get("job_id")
            with st.spinner("Golden set running…"):
                for _ in range(600):
                    resp = api_client.get_eval_status(job_id)
                    if resp.get("status") == "done":
                        st.success("Golden CI complete")
                        st.json(resp.get("result", {}))
                        break
                    if resp.get("status") == "error":
                        st.error(resp.get("error"))
                        break
                    time.sleep(2)
        except api_client.APIError as e:
            st.error(e.message)

    section_header("Compare versions")
    history = api_client.get_eval_history() if backend_ok else []
    if not history:
        st.info("No eval history yet — run RAGAS eval first.")
    else:
        options = {r.get("version", r.get("timestamp", "?")): r for r in history}
        c1, c2 = st.columns(2)
        with c1:
            baseline = st.selectbox("Baseline", list(options.keys()))
        with c2:
            candidate = st.selectbox("Candidate", list(options.keys()))
        if st.button("Compare runs", type="primary"):
            try:
                diff = api_client.compare_eval_runs(baseline, candidate)
                if diff.get("regressions_found"):
                    st.warning("Regressions detected")
                else:
                    st.success("No regressions within tolerance")
                if diff.get("regressions"):
                    st.dataframe(pd.DataFrame(diff["regressions"]), use_container_width=True)
            except Exception as e:
                st.error(str(e))

        section_header("Run details")
        labels = {
            f"{r.get('version', '?')} · P@3 {r.get('retrieval_precision_at_3', 0):.2f}": r
            for r in history
        }
        pick = st.selectbox("Historical run", list(labels.keys()))
        render_per_question_diagnostics(labels[pick], title="Per-question breakdown")

    section_header("Golden set CI")
    try:
        ci = api_client.get_golden_status()
        sv = ci.get("status", "not_yet_run")
        c1, c2, c3 = st.columns(3)
        render_stat_card("Status", sv.upper(), c1)
        render_stat_card("Score", f"{ci.get('score', 0):.0%}" if ci.get("score") is not None else "—", c2)
        render_stat_card("Passed", f"{ci.get('passed', '—')}/{ci.get('total', '—')}", c3)
        if sv == "fail" and ci.get("failed_questions"):
            with st.expander("Failed questions"):
                for q in ci["failed_questions"]:
                    st.markdown(f"- {q}")
        per_repo = ci.get("per_repo") or []
        if per_repo:
            st.dataframe(pd.DataFrame(per_repo), use_container_width=True, hide_index=True)
        if ci.get("skipped_fixtures"):
            st.caption(f"Skipped fixtures: {', '.join(ci['skipped_fixtures'])}")
    except Exception:
        st.info("Golden CI not run yet — click **Run Golden CI** above.")

elif page == "Platform":
    section_header("Platform & billing", "Usage, subscription, audit trail")
    if not backend_ok:
        render_alert("info", "Start the backend to view platform data.")
    else:
        try:
            usage = api_client.get_platform_usage()
            sub = api_client.get_billing_subscription()
            c1, c2, c3, c4 = st.columns(4)
            render_stat_card("Org", usage.get("org_id", "—"), c1)
            render_stat_card("Plan", sub.get("plan_name", "Free"), c2)
            metrics = usage.get("metrics") or {}
            render_stat_card("Chat", str(metrics.get("chat", 0)), c3)
            render_stat_card("Ingest", str(metrics.get("ingest", 0)), c4)
            st.caption("Admin console: http://localhost:3000")
            with st.expander("Usage details", expanded=False):
                st.json(usage)
            with st.expander("Subscription", expanded=False):
                st.json(sub)
            audit = api_client.get_platform_audit()
            if audit:
                st.dataframe(pd.DataFrame(audit), use_container_width=True, hide_index=True)
        except api_client.APIError as e:
            st.error(e.message)

render_footer()
