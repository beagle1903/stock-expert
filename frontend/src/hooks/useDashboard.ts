import { useCallback, useEffect, useState } from "react";
import type { DashboardRepository } from "../data/dashboardRepository";
import type { DashboardData } from "../domain/dashboard";

type LoadStatus = "loading" | "loaded" | "error";

export function useDashboard(repository: DashboardRepository) {
  const [data, setData] = useState<DashboardData | null>(null);
  const [status, setStatus] = useState<LoadStatus>("loading");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      setData(await repository.load());
      setStatus("loaded");
    } catch (caught) {
      setData(null);
      setStatus("error");
      setError(caught instanceof Error ? caught.message : "Persisted evidence could not be loaded.");
    }
  }, [repository]);

  useEffect(() => {
    void load();
  }, [load]);

  return { data, status, error, reload: load };
}
