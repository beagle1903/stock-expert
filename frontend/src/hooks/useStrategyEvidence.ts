import { useCallback, useEffect, useRef, useState } from "react";
import type { StrategyEvidenceRepository } from "../data/strategyEvidenceRepository";
import { createLatestRequestGuard } from "../data/strategyEvidenceViewModel.mjs";
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
  const requestGuard = useRef(createLatestRequestGuard());

  const load = useCallback(async () => {
    const requestId = requestGuard.current.begin();
    setStatus("loading");
    setError(null);
    try {
      const nextEvidence = await repository.load(window);
      if (!requestGuard.current.isLatest(requestId)) return;
      setEvidence(nextEvidence);
      setStatus("loaded");
    } catch (loadError) {
      if (!requestGuard.current.isLatest(requestId)) return;
      setStatus("error");
      setError(loadError instanceof Error ? loadError.message : "Strategy evidence could not be loaded.");
    }
  }, [repository, window]);

  useEffect(() => {
    if (enabled) {
      void load();
    } else {
      requestGuard.current.invalidate();
    }
  }, [enabled, load]);

  return { evidence, status, error, window, setWindow, reload: load };
}
