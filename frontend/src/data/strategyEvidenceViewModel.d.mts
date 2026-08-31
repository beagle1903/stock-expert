import type { EvidenceWindow, StrategyEvidence, StrategySummary, EvidenceMetricSummary } from "../domain/strategyEvidence";

export const evidenceWindowOptions: EvidenceWindow[];
export function evidenceDisplayState(evidence: StrategyEvidence | null): {
  kind: "empty" | "partial" | "complete";
  notices: string[];
};
export function findStrategySummary(
  evidence: StrategyEvidence | null,
  strategy: "score_ranked" | "bucketed",
): StrategySummary | null;
export function findEvidencePattern(
  evidence: StrategyEvidence | null,
  pattern: string,
): (EvidenceMetricSummary & { pattern: string }) | null;
