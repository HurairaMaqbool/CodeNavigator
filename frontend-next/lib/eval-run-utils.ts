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

export function sortRunsByTimestampDesc(runs: EvalRun[]): EvalRun[] {
  return [...runs].sort((a, b) => {
    const timeA = a.timestamp ? new Date(a.timestamp).getTime() : 0;
    const timeB = b.timestamp ? new Date(b.timestamp).getTime() : 0;
    return timeB - timeA;
  });
}

export function normalizeEvalHistory(runs: EvalRun[]): EvalRun[] {
  return sortRunsByTimestampDesc(runs.map(normalizeEvalRun));
}

/** Pick the best run to display scores for (defaults to most recent run by timestamp). */
export function pickDisplayRun(
  runs: EvalRun[],
  preferred?: EvalRun | null,
): EvalRun | null {
  const sorted = sortRunsByTimestampDesc(runs);
  if (preferred?.ragas_scores) return normalizeEvalRun(preferred);
  for (const run of sorted) {
    if (run.ragas_scores) return normalizeEvalRun(run);
  }
  return null;
}
