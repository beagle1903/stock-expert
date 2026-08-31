export const evidenceWindowOptions = ["5", "10", "20", "all"];

export function createLatestRequestGuard() {
  let latestRequestId = 0;
  return {
    begin() {
      latestRequestId += 1;
      return latestRequestId;
    },
    isLatest(requestId) {
      return requestId === latestRequestId;
    },
    invalidate() {
      latestRequestId += 1;
    },
  };
}

export function appContentMode(activeView, hasDashboardData) {
  if (activeView === "diagnostics") return "strategy_lab";
  return hasDashboardData ? "dashboard" : "dashboard_unavailable";
}

export function evidenceDisplayState(evidence) {
  if (!evidence || evidence.status === "empty") {
    return { kind: "empty", notices: [] };
  }
  const notices = [];
  if (evidence.comparison.status === "partial") {
    notices.push("Incomplete or unpaired pilot sessions are excluded from the comparison.");
  } else if (evidence.comparison.status === "unavailable") {
    notices.push("No persisted paired pilot sessions are available in this review window.");
  }
  if (evidence.candidateEvidence.status !== "available") {
    notices.push("Some reviews do not contain persisted candidate outcomes.");
  }
  if (evidence.breadth.status !== "available") {
    notices.push("Some reviews do not identify a signal snapshot for breadth evidence.");
  }
  return { kind: notices.length ? "partial" : "complete", notices };
}

export function findStrategySummary(evidence, strategy) {
  return evidence?.comparison.strategies.find((row) => row.strategy === strategy) ?? null;
}

export function findEvidencePattern(evidence, pattern) {
  return evidence?.candidateEvidence.patterns.find((row) => row.pattern === pattern) ?? null;
}
