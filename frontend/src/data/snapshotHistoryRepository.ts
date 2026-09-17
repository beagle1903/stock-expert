import type { SnapshotDetail, SnapshotHistoryItem } from "../domain/snapshotHistory";

interface SnapshotHistoryResponse {
  snapshots?: SnapshotHistoryItem[];
  error?: string;
}

interface SnapshotDetailResponse {
  snapshot?: SnapshotDetail;
  error?: string;
}

export interface SnapshotHistoryRepository {
  loadHistory(): Promise<SnapshotHistoryItem[]>;
  loadDetail(snapshotId: number): Promise<SnapshotDetail>;
}

export const snapshotHistoryRepository: SnapshotHistoryRepository = {
  async loadHistory() {
    const response = await fetch("/api/snapshots/history");
    const payload = await response.json().catch(() => ({})) as SnapshotHistoryResponse;
    if (!response.ok) {
      throw new Error(payload.error ?? `Request failed with status ${response.status}.`);
    }
    if (!payload.snapshots) {
      throw new Error("Snapshot history was not returned by the local API.");
    }
    return payload.snapshots;
  },

  async loadDetail(snapshotId) {
    const response = await fetch(`/api/snapshots/${snapshotId}`);
    const payload = await response.json().catch(() => ({})) as SnapshotDetailResponse;
    if (!response.ok) {
      throw new Error(payload.error ?? `Request failed with status ${response.status}.`);
    }
    if (!payload.snapshot) {
      throw new Error("The selected snapshot is no longer available.");
    }
    return payload.snapshot;
  },
};
