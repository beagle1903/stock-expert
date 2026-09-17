export function persistedRowsLabel() {
  return "Persisted rows";
}

export function coverageRegressionNotice(priorSnapshotId) {
  return `Coverage is lower than snapshot #${priorSnapshotId}.`;
}

export function mappingFailureIncreaseNotice(priorSnapshotId) {
  return `Unmapped rows increased versus snapshot #${priorSnapshotId}.`;
}

export function snapshotDetailForSelection(detail, selectedId) {
  if (detail == null || selectedId == null || detail.id !== selectedId) return null;
  return detail;
}

export function snapshotNotices(detail) {
  if (!detail) return [];
  const notices = [];
  if (detail.provenanceStatus === "not_captured") {
    notices.push("Provenance was not captured for this snapshot.");
  }
  if (detail.comparison?.status === "unavailable") {
    notices.push("No prior published snapshot.");
  }
  if (detail.comparison?.coverageRegression && detail.comparison.priorSnapshotId != null) {
    notices.push(coverageRegressionNotice(detail.comparison.priorSnapshotId));
  }
  if (detail.comparison?.mappingFailureIncrease && detail.comparison.priorSnapshotId != null) {
    notices.push(mappingFailureIncreaseNotice(detail.comparison.priorSnapshotId));
  }
  return notices;
}
