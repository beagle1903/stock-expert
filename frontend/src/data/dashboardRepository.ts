import type { DashboardData, ReviewSummary } from "../domain/dashboard";

export interface DashboardRepository {
  load(): Promise<DashboardData>;
}

interface LatestReviewResponse {
  review: ReviewSummary | null;
  error?: string;
}

interface LatestPicksResponse {
  dashboard: Omit<DashboardData, "review"> | null;
  error?: string;
}

export const dashboardRepository: DashboardRepository = {
  async load() {
    const [picksResponse, reviewResponse] = await Promise.all([
      fetch("/api/picks/latest"),
      fetch("/api/reviews/latest"),
    ]);
    const picksPayload = await picksResponse.json().catch(() => ({})) as LatestPicksResponse;
    const reviewPayload = await reviewResponse.json().catch(() => ({})) as LatestReviewResponse;
    if (!picksResponse.ok) {
      throw new Error(picksPayload.error ?? `Request failed with status ${picksResponse.status}.`);
    }
    if (!reviewResponse.ok) {
      throw new Error(reviewPayload.error ?? `Request failed with status ${reviewResponse.status}.`);
    }
    if (!picksPayload.dashboard) {
      throw new Error("No persisted snapshot is available yet.");
    }
    return { ...picksPayload.dashboard, review: reviewPayload.review };
  },
};
