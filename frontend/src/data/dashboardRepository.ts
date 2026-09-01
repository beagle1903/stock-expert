import type { DashboardData, ReviewHistoryItem, ReviewSummary } from "../domain/dashboard";
import type { StrategyPlayback } from "../domain/strategyPlayback";

export interface DashboardRepository {
  load(): Promise<DashboardData>;
  loadReview(reviewId: number): Promise<ReviewSummary>;
  loadPlayback(reviewId: number): Promise<StrategyPlayback>;
}

interface LatestReviewResponse {
  review: ReviewSummary | null;
  error?: string;
}

interface LatestPicksResponse {
  dashboard: Omit<DashboardData, "review" | "reviewHistory"> | null;
  error?: string;
}

interface ReviewHistoryResponse {
  reviews: ReviewHistoryItem[];
  error?: string;
}

interface StrategyPlaybackResponse {
  playback?: StrategyPlayback;
  error?: string;
}

export const dashboardRepository: DashboardRepository = {
  async load() {
    const [picksResponse, reviewResponse, historyResponse] = await Promise.all([
      fetch("/api/picks/latest"),
      fetch("/api/reviews/latest"),
      fetch("/api/reviews/history"),
    ]);
    const picksPayload = await picksResponse.json().catch(() => ({})) as LatestPicksResponse;
    const reviewPayload = await reviewResponse.json().catch(() => ({})) as LatestReviewResponse;
    const historyPayload = await historyResponse.json().catch(() => ({})) as ReviewHistoryResponse;
    if (!picksResponse.ok) {
      throw new Error(picksPayload.error ?? `Request failed with status ${picksResponse.status}.`);
    }
    if (!reviewResponse.ok) {
      throw new Error(reviewPayload.error ?? `Request failed with status ${reviewResponse.status}.`);
    }
    if (!historyResponse.ok) {
      throw new Error(historyPayload.error ?? `Request failed with status ${historyResponse.status}.`);
    }
    if (!picksPayload.dashboard) {
      throw new Error("No persisted snapshot is available yet.");
    }
    return {
      ...picksPayload.dashboard,
      review: reviewPayload.review,
      reviewHistory: historyPayload.reviews,
    };
  },

  async loadReview(reviewId) {
    const response = await fetch(`/api/reviews/${reviewId}`);
    const payload = await response.json().catch(() => ({})) as LatestReviewResponse;
    if (!response.ok) {
      throw new Error(payload.error ?? `Request failed with status ${response.status}.`);
    }
    if (!payload.review) {
      throw new Error("The selected persisted review is no longer available.");
    }
    return payload.review;
  },

  async loadPlayback(reviewId) {
    const response = await fetch(`/api/strategy-playback/${reviewId}`);
    const payload = await response.json().catch(() => ({})) as StrategyPlaybackResponse;
    if (!response.ok) {
      throw new Error(payload.error ?? `Request failed with status ${response.status}.`);
    }
    if (!payload.playback) {
      throw new Error("The selected historical playback is no longer available.");
    }
    return payload.playback;
  },
};
