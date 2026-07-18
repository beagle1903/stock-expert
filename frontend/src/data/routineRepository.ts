import type { RoutinePreview, RoutineRunRequest, RoutineRunResult } from "../domain/routine";

async function readJson<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => ({})) as T & { error?: string };
  if (!response.ok) {
    throw new Error(payload.error ?? `Request failed with status ${response.status}.`);
  }
  return payload;
}

export interface RoutineRepository {
  preview(signalDate: string, signal?: AbortSignal): Promise<RoutinePreview>;
  run(request: RoutineRunRequest): Promise<RoutineRunResult>;
}

export const routineRepository: RoutineRepository = {
  async preview(signalDate, signal) {
    const query = new URLSearchParams({ signal_date: signalDate });
    return readJson<RoutinePreview>(
      await fetch(`/api/routine/preview?${query.toString()}`, { signal }),
    );
  },

  async run(request) {
    return readJson<RoutineRunResult>(
      await fetch("/api/routine", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      }),
    );
  },
};
