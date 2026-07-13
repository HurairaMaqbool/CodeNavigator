import type { EvalRun, PerQuestionDiagnostic } from "@/lib/types";

/** Normalize eval history rows from API (per_question may live under diagnostics). */
export function normalizeEvalRun(run: EvalRun): EvalRun {
  const diag = run.diagnostics ?? {};
  const perQuestion =
    run.per_question ??
    (diag as { per_question?: PerQuestionDiagnostic[] }).per_question ??
    [];

  const normalizedRows = perQuestion.map((row) => ({
    ...row,
    hit: row.hit ?? row.gt_hit,
    confidence: row.confidence ?? row.confidence_score,
  }));

  return {
    ...run,
    per_question: normalizedRows,
    diagnostics: {
      ...diag,
      question_count: diag.question_count ?? normalizedRows.length,
    },
  };
}

export function normalizeEvalHistory(runs: EvalRun[]): EvalRun[] {
  return runs.map(normalizeEvalRun);
}

/** Pick the best run to display scores for (prefers rows with per-question data). */
export function pickDisplayRun(
  runs: EvalRun[],
  preferred?: EvalRun | null,
): EvalRun | null {
  if (preferred?.ragas_scores) return normalizeEvalRun(preferred);
  for (const run of runs) {
    if (run.ragas_scores) return normalizeEvalRun(run);
  }
  return null;
}
