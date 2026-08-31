export type EvidenceWindow = "5" | "10" | "20" | "all";
export type EvidenceAvailability = "available" | "partial" | "unavailable";

export interface EvidenceMetricSummary {
  count: number;
  wins: number;
  averageReturn: number;
  winRate: number;
}

export interface StrategySummary {
  strategy: "score_ranked" | "bucketed";
  sessionCount: number;
  pickCount: number;
  evaluatedCount: number;
  wins: number;
  averageSessionReturn: number;
  compoundedReturn: number;
  pickWinRate: number;
}

export interface PilotSessionArm {
  pickCount: number;
  evaluatedCount: number;
  wins: number;
  averageReturn: number;
  isComplete: boolean;
}

export interface PilotSessionEvidence {
  signalSnapshotId: number;
  signalDate: string;
  reviewDate: string;
  scoreRanked: PilotSessionArm | null;
  bucketed: PilotSessionArm | null;
  pairStatus: "complete" | "incomplete" | "unpaired";
}

export interface StrategyEvidence {
  status: "available" | "empty";
  window: {
    requested: EvidenceWindow;
    availableReviewCount: number;
    includedReviewCount: number;
    startReviewDate: string | null;
    endReviewDate: string | null;
  };
  pilot: {
    name: string;
    status: "not_started" | "active" | "promoted" | "rolled_back" | "failed";
    selectedStrategy: "score_ranked" | "bucketed";
    startedSignalDate?: string;
    completedSessions: number;
    bucketedSessionWins: number;
    scoreCompoundedReturn: number;
    bucketedCompoundedReturn: number;
    compoundedEdge: number;
    momentumWeight?: number;
    volumeWeight?: number;
    decisionReason: string;
    thresholds: {
      sessionTarget: number;
      minimumBucketedSessionWins: number;
      promotionEdge: number;
      rollbackEdge: number;
    };
  };
  comparison: {
    status: EvidenceAvailability;
    completePairedSessions: number;
    incompletePairedSessions: number;
    unpairedSessions: number;
    bucketedSessionWins: number;
    strategies: StrategySummary[];
    sessions: PilotSessionEvidence[];
  };
  candidateEvidence: {
    status: EvidenceAvailability;
    capturedReviewCount: number;
    missingReviewCount: number;
    sessionCount: number;
    candidateCount: number;
    rankBands: Array<{ band: string } & EvidenceMetricSummary>;
    cutoffAnalysis: {
      cutoffs: Array<{ cutoff: string } & EvidenceMetricSummary>;
      bestCutoff: string | null;
      minimumObservations: number;
    };
    patterns: Array<{ pattern: string } & EvidenceMetricSummary>;
    setupPenalty: {
      averagePenalty: number;
      penalized: EvidenceMetricSummary;
      unpenalized: EvidenceMetricSummary;
    };
    strategies: Array<{ strategy: string } & EvidenceMetricSummary>;
    note: string;
  };
  breadth: {
    status: EvidenceAvailability;
    availableSessionCount: number;
    unavailableSessionCount: number;
    averageAdvancerRatio: number | null;
    minimumAdvancerRatio: number | null;
    maximumAdvancerRatio: number | null;
    sessions: Array<{
      reviewId: number;
      signalDate: string;
      reviewDate: string;
      signalSnapshotId: number | null;
      status: "available" | "unavailable";
      universeCount: number;
      advancerCount: number;
      advancerRatio: number | null;
    }>;
  };
}
