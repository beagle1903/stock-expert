import type { SnapshotDetail } from "../domain/snapshotHistory";

export function persistedRowsLabel(): string;
export function coverageRegressionNotice(priorSnapshotId: number): string;
export function mappingFailureIncreaseNotice(priorSnapshotId: number): string;
export function snapshotNotices(detail: SnapshotDetail | null): string[];
