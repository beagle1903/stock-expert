import type { ReviewSummary } from "./dashboard";

export type PlaybackAvailability = "available" | "partial" | "unavailable";

export interface StrategyPlaybackPick {
  basketOrder: number;
  ticker: string;
  score: number;
  candidateRank: number | null;
  selectionBucket: string | null;
  signals: {
    momentum: number;
    volume: number;
    technical: number;
    fundamental: number;
    quality: number;
    setupPenalty: number;
  } | null;
  outcome: {
    openPrice: number;
    closePrice: number;
    returnPct: number;
    won: boolean;
  };
}

export interface StrategyPlayback {
  review: ReviewSummary;
  signal: {
    status: "available" | "unavailable";
    snapshotId: number | null;
    signalDate: string;
    targetTradeDate: string;
    importedAt: string | null;
    source: string | null;
    universeCount: number;
    advancerCount: number;
    advancerRatio: number | null;
  };
  strategy: {
    version: string;
    selectedStrategy: "score_ranked" | "bucketed";
    momentumWeight: number;
    volumeWeight: number;
    weightDate: string | null;
  };
  basket: {
    status: "available" | "unavailable";
    attributionStatus: PlaybackAvailability;
    picks: StrategyPlaybackPick[];
  };
  pilotComparison: {
    status: "available" | "unavailable";
    arms: Array<{
      strategy: "score_ranked" | "bucketed";
      pickCount: number;
      evaluatedCount: number;
      wins: number;
      averageReturn: number;
      isComplete: boolean;
    }>;
  };
}
