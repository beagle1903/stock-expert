import type { DashboardData } from "../domain/dashboard";
import { mockDashboard } from "./mockDashboard";

export interface DashboardRepository {
  load(): Promise<DashboardData>;
}

export const mockDashboardRepository: DashboardRepository = {
  async load() {
    await new Promise((resolve) => window.setTimeout(resolve, 240));
    return structuredClone(mockDashboard);
  },
};
