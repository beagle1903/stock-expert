import { useCallback, useEffect, useState } from "react";
import type { StrategyEvidenceRepository } from "../data/strategyEvidenceRepository";
import type { EvidenceWindow, StrategyEvidence } from "../domain/strategyEvidence";

type EvidenceLoadStatus = "idle" | "loading" | "loaded" | "error";

export function useStrategyEvidence(
  repository: StrategyEvidenceRepository,
  enabled: boolean,
) {
  const [window, setWindow] = useState<EvidenceWindow>("10");
  const [evidence, setEvidence] = useState<StrategyEvidence | null>(null);
  const [status, setStatus] = useState<EvidenceLoadStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      setEvidence(await repository.load(window));
      setStatus("loaded");
    } catch (loadError) {
      setStatus("error");
      setError(loadError instanceof Error ? loadError.message : "Strategy evidence could not be loaded.");
    }
  }, [repository, window]);

  useEffect(() => {
    if (enabled) void load();
  }, [enabled, load]);

  return { evidence, status, error, window, setWindow, reload: load };
}
