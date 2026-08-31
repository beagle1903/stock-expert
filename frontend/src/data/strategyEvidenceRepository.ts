import type { EvidenceWindow, StrategyEvidence } from "../domain/strategyEvidence";

interface StrategyEvidenceResponse {
  evidence?: StrategyEvidence;
  error?: string;
}

export interface StrategyEvidenceRepository {
  load(window: EvidenceWindow): Promise<StrategyEvidence>;
}

export const strategyEvidenceRepository: StrategyEvidenceRepository = {
  async load(window) {
    const response = await fetch(`/api/strategy-evidence?window=${window}`);
    const payload = await response.json().catch(() => ({})) as StrategyEvidenceResponse;
    if (!response.ok) {
      throw new Error(payload.error ?? `Request failed with status ${response.status}.`);
    }
    if (!payload.evidence) {
      throw new Error("Strategy evidence was not returned by the local API.");
    }
    return payload.evidence;
  },
};
