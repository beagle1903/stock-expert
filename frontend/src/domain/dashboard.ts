export type ViewKey = "overview" | "picks" | "reviews" | "diagnostics" | "runs";
export type RiskLevel = "high" | "medium" | "low";

export interface PickSignals {
  momentum: number;
  volume: number;
  technical: number;
  fundamental: number;
  quality: number;
  setupPenalty: number;
  maTrend: number;
  liquidity: number;
  totalBoost: number;
  netAdjustment: number;
}

export interface Pick {
  rank: number;
  ticker: string;
  score: number;
  risk: RiskLevel;
  horizon: "intraday";
  selectionBucket: "score_ranked";
  signals: PickSignals;
}

export interface ReviewOutcome {
  ticker: string;
  returnPct: number;
  won: boolean;
}

export type MissedMoverClassification = "actionable" | "non_actionable";
export type MissedMoversStatus = "captured" | "not_captured";

export type MissedMoverSignals = Omit<PickSignals, "totalBoost" | "netAdjustment">;

export interface MissedMover {
  ticker: string;
  returnPct: number;
  classification: MissedMoverClassification;
  reason: string;
  attribution: {
    dataStatus: string;
    candidateRank: number | null;
    selectionNote: string;
    selectionBucket: string | null;
    signals: MissedMoverSignals | null;
    adjustments: {
      totalBoost: number;
      netAdjustment: number;
    } | null;
  };
}

export interface ReviewSummary {
  id: number;
  signalDate: string;
  reviewDate: string;
  averageReturn: number;
  winRate: number;
  wins: number;
  pickCount: number;
  minimumWinReturn: number;
  outcomes: ReviewOutcome[];
  missedMoversStatus: MissedMoversStatus;
  missedMovers: MissedMover[];
}

export interface ReviewHistoryItem {
  id: number;
  signalDate: string;
  reviewDate: string;
  averageReturn: number;
  winRate: number;
  wins: number;
  pickCount: number;
}

export interface RunStep {
  id: number;
  label: string;
  detail: string;
}

export interface DashboardData {
  signalDate: string;
  tradeDate: string;
  snapshot: {
    id: number;
    importedAt: string;
    source: "daily_csv";
    status: "persisted";
    priceBasis: "previous_close_to_latest";
  };
  exposure: {
    universeCount: number;
    advancerRatio: number | null;
    pickCountCap: number;
    policy: string;
  };
  picks: Pick[];
  review: ReviewSummary | null;
  reviewHistory: ReviewHistoryItem[];
  runSteps: RunStep[];
}
