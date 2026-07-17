export type ViewKey = "overview" | "picks" | "reviews" | "diagnostics" | "runs";
export type PreviewState = "loaded" | "loading" | "empty" | "error";
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
    advancerRatio: number;
    pickCountCap: number;
    policy: "normal";
  };
  picks: Pick[];
  review: ReviewSummary;
  runSteps: RunStep[];
}
