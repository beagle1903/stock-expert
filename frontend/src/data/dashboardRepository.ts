import type { DashboardData, ReviewSummary } from "../domain/dashboard";
import { mockDashboard } from "./mockDashboard";

export interface DashboardRepository {
  load(): Promise<DashboardData>;
}

interface LatestReviewResponse {
  review: ReviewSummary | null;
  error?: string;
}

export const dashboardRepository: DashboardRepository = {
  async load() {
    const response = await fetch("/api/reviews/latest");
    const payload = await response.json().catch(() => ({})) as LatestReviewResponse;
    if (!response.ok) {
      throw new Error(payload.error ?? `Request failed with status ${response.status}.`);
    }
    return { ...structuredClone(mockDashboard), review: payload.review };
  },
};
