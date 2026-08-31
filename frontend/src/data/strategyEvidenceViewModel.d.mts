import type { EvidenceWindow, StrategyEvidence, StrategySummary, EvidenceMetricSummary } from "../domain/strategyEvidence";
import type { ViewKey } from "../domain/dashboard";

export const evidenceWindowOptions: EvidenceWindow[];
export interface LatestRequestGuard {
  begin(): number;
  isLatest(requestId: number): boolean;
  invalidate(): void;
}
export function createLatestRequestGuard(): LatestRequestGuard;
export function appContentMode(
  activeView: ViewKey,
  hasDashboardData: boolean,
): "strategy_lab" | "dashboard" | "dashboard_unavailable";
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
