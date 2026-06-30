"""
app/evaluation/run_eval.py
--------------------------
RAGAS Dashboard Harness.

Evaluates the real `answer_question` agent loop against `tests/eval_set.json`
using the free-tier wrappers defined in `ragas_providers.py`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from datasets import Dataset
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall

from app.config import settings
from app.observability.logging_config import logger
from app.agent.semantic_cache import answer_question_cached
from app.evaluation.ragas_providers import get_judge_llm, get_judge_embeddings
from app.evaluation.compare_runs import append_to_history

def build_ragas_dataset(eval_set_path: str) -> tuple[Dataset, dict[str, Any]]:
    """
    Reads the eval set, invokes the real agent pipeline, and constructs the dataset.
    
    Precondition: The repos referenced in eval_set.json MUST be ingested prior to
    running this, as this uses the actual live vector/graph stores.
    """
    path = Path(eval_set_path)
    if not path.exists():
        raise FileNotFoundError(f"Eval set not found at {eval_set_path}")
        
    eval_data = json.loads(path.read_text(encoding="utf-8"))
    
    questions = []
    answers = []
    contexts = []
    ground_truths = []
    
    # Supplementary metrics tracking
    total_conf = 0.0
    total_invalid = 0.0
    gated_count = 0
    p_at_3_sum = 0.0
    
    valid_records = 0
    
    for row in eval_data:
        q = row["question"]
        repo_id = row["repo_id"]
        gt = row.get("ground_truth_answer_summary", "")
        gt_files = row.get("ground_truth_files", [])
        
        # Invoke REAL pipeline (using answer_question_cached to simulate real user load)
        try:
            # Bypass cache for true eval using force if needed, but we assume
            # evaluating the cache is part of evaluating the pipeline.
            # To strictly evaluate the LLM, you might wipe the cache first.
            ans_res = answer_question_cached(q, repo_id)
        except Exception as e:
            logger.error("eval_question_failed", question=q, error=str(e))
            continue
            
        questions.append(q)
        answers.append(ans_res["answer"])
        
        # Assemble retrieved context (flatten sources into strings for RAGAS)
        ctx_list = []
        retrieved_files = []
        for s in ans_res.get("sources", []):
            retrieved_files.append(s["file_path"])
            ctx_list.append(f"File: {s['file_path']}\n{s.get('function_name', '')}")
            
        contexts.append(ctx_list)
        ground_truths.append([gt])
        
        # Supplementary metrics
        total_conf += ans_res.get("confidence_score", 0.0)
        total_invalid += ans_res.get("invalid_reference_ratio", 0.0)
        if ans_res.get("gated"):
            gated_count += 1
            
        # P@3 calculation
        top_3 = retrieved_files[:3]
        hits = sum(1 for f in top_3 if f in gt_files)
        p_at_3_sum += (hits / min(len(gt_files) or 1, 3))
        
        valid_records += 1

    if valid_records == 0:
        raise ValueError("No questions were successfully evaluated.")

    ragas_ds = Dataset.from_dict({
        "question": questions,
        "answer": answers,
        "contexts": contexts,
        "ground_truth": ground_truths
    })
    
    supp_metrics = {
        "mean_confidence": round(total_conf / valid_records, 2),
        "mean_invalid_ratio": round(total_invalid / valid_records, 2),
        "gated_rate": round(gated_count / valid_records, 2),
        "precision_at_3": round(p_at_3_sum / valid_records, 2),
        "total_records": valid_records
    }
    
    return ragas_ds, supp_metrics


def run_eval(eval_set_path: str = "tests/eval_set.json") -> dict[str, Any]:
    """
    Executes the full RAGAS eval + supplementary metrics and logs history.
    """
    judge_llm = get_judge_llm()
    judge_embeddings = get_judge_embeddings()
    
    dataset, supp = build_ragas_dataset(eval_set_path)
    
    results = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=judge_llm,
        embeddings=judge_embeddings
    )
    
    ragas_scores = {}
    metrics_list = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]
    for m in metrics_list:
        try:
            scores = results[m]
            valid_scores = [float(v) for v in scores if v == v]
            ragas_scores[m] = sum(valid_scores) / len(valid_scores) if valid_scores else 0.0
        except Exception:
            ragas_scores[m] = 0.0
    
    final_payload = {
        "ragas_scores": ragas_scores,
        "supplementary": supp
    }
    
    append_to_history(final_payload)
    
    return final_payload
