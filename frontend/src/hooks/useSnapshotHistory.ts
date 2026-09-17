import { useCallback, useEffect, useRef, useState } from "react";
import type { SnapshotHistoryRepository } from "../data/snapshotHistoryRepository";
import { createLatestRequestGuard } from "../data/strategyEvidenceViewModel.mjs";
import type { SnapshotDetail, SnapshotHistoryItem } from "../domain/snapshotHistory";

type LoadStatus = "idle" | "loading" | "loaded" | "error";

export function useSnapshotHistory(
  repository: SnapshotHistoryRepository,
  enabled: boolean,
) {
  const [history, setHistory] = useState<SnapshotHistoryItem[]>([]);
  const [detail, setDetail] = useState<SnapshotDetail | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [status, setStatus] = useState<LoadStatus>("idle");
  const [detailStatus, setDetailStatus] = useState<LoadStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const historyGuard = useRef(createLatestRequestGuard());
  const detailGuard = useRef(createLatestRequestGuard());

  const loadHistory = useCallback(async () => {
    const requestId = historyGuard.current.begin();
    setStatus("loading");
    setError(null);
    try {
      const snapshots = await repository.loadHistory();
      if (!historyGuard.current.isLatest(requestId)) return;
      setHistory(snapshots);
      setStatus("loaded");
      setSelectedId((current) => {
        if (current !== null && snapshots.some((row) => row.id === current)) return current;
        return snapshots[0]?.id ?? null;
      });
    } catch (loadError) {
      if (!historyGuard.current.isLatest(requestId)) return;
      setStatus("error");
      setError(loadError instanceof Error ? loadError.message : "Snapshot history could not be loaded.");
    }
  }, [repository]);

  useEffect(() => {
    if (enabled) {
      void loadHistory();
    } else {
      historyGuard.current.invalidate();
      detailGuard.current.invalidate();
    }
  }, [enabled, loadHistory]);

  useEffect(() => {
    if (!enabled || selectedId === null) return;
    const requestId = detailGuard.current.begin();
    setDetailStatus("loading");
    setDetailError(null);
    setDetail((current) => (current?.id === selectedId ? current : null));
    void repository.loadDetail(selectedId)
      .then((nextDetail) => {
        if (!detailGuard.current.isLatest(requestId)) return;
        setDetail(nextDetail);
        setDetailStatus("loaded");
      })
      .catch((loadError) => {
        if (!detailGuard.current.isLatest(requestId)) return;
        setDetail(null);
        setDetailStatus("error");
        setDetailError(loadError instanceof Error ? loadError.message : "The selected snapshot could not be loaded.");
      });
  }, [enabled, repository, selectedId]);

  return {
    history,
    detail,
    selectedId,
    status,
    detailStatus,
    error,
    detailError,
    selectSnapshot: setSelectedId,
    reload: loadHistory,
  };
}
