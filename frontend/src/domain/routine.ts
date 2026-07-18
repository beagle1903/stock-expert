export type RoutineFileStatus = "ready" | "missing" | "empty" | "stale";

export interface RoutineInputFile {
  name: string;
  exists: boolean;
  sizeBytes: number;
  modifiedAt: string | null;
  status: RoutineFileStatus;
}

export interface RoutineMarketContext {
  tags: Array<{ date: string; tag: string }>;
  selection_policy: string;
  interpretation: string | null;
}

export interface RoutinePreview {
  requestedSignalDate: string;
  resolvedSignalDate: string;
  targetTradeDate: string;
  requestedWasTradingSession: boolean;
  marketContext: RoutineMarketContext;
  calendarSource: "repository_confirmed";
  files: RoutineInputFile[];
  ready: boolean;
  blockingIssues: string[];
  warnings: string[];
  confirmationToken: string;
}

export interface RoutineRunRequest {
  requestedSignalDate: string;
  confirmationToken: string;
  confirmed: true;
}

export interface RoutineRunResult {
  ok: true;
  requestedSignalDate: string;
  signalDate: string;
  targetTradeDate: string;
  snapshotId: number | null;
  pickCount: number;
  reviewRunId: number | null;
  reviewSignalDate: string;
  reviewDate: string;
  completedAt: string;
  outputTail: string;
}
