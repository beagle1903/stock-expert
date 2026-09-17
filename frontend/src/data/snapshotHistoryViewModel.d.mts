import type { SnapshotDetail } from "../domain/snapshotHistory";

export function persistedRowsLabel(): string;
export function coverageRegressionNotice(priorSnapshotId: number): string;
export function mappingFailureIncreaseNotice(priorSnapshotId: number): string;
export function snapshotDetailForSelection(
  detail: SnapshotDetail | null,
  selectedId: number | null,
): SnapshotDetail | null;
export function snapshotNotices(detail: SnapshotDetail | null): string[];
