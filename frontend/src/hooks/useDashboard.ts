import { useCallback, useEffect, useState } from "react";
import type { DashboardRepository } from "../data/dashboardRepository";
import type { DashboardData } from "../domain/dashboard";

type LoadStatus = "loading" | "loaded" | "error";

export function useDashboard(repository: DashboardRepository) {
  const [data, setData] = useState<DashboardData | null>(null);
  const [status, setStatus] = useState<LoadStatus>("loading");

  const load = useCallback(async () => {
    setStatus("loading");
    try {
      setData(await repository.load());
      setStatus("loaded");
    } catch {
      setStatus("error");
    }
  }, [repository]);

  useEffect(() => {
    void load();
  }, [load]);

  return { data, status, reload: load };
}
