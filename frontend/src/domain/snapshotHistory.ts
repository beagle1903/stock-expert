export type ProvenanceStatus = "captured" | "not_captured";
export type PublicationResult = "published";
export type SnapshotComparisonStatus = "available" | "unavailable" | "not_captured";

export interface SnapshotComparisonDeltas {
  tickerCoverage: number | null;
  rowsRead: number | null;
  distinctTickers: number | null;
  skippedUnmappedCount: number | null;
  skippedMalformedCount: number | null;
}

export interface SnapshotComparison {
  status: SnapshotComparisonStatus;
  priorSnapshotId: number | null;
  coverageRegression: boolean;
  mappingFailureIncrease: boolean;
  deltas: SnapshotComparisonDeltas | null;
}

export interface SnapshotHistoryItem {
  id: number;
  snapshotDate: string;
  importedAt: string;
  source: string;
  sourceDir: string;
  provenanceStatus: ProvenanceStatus;
  publicationResult: PublicationResult;
  rowsRead: number | null;
  distinctTickers: number | null;
  skippedUnmappedCount: number | null;
  skippedMalformedCount: number | null;
  tickerCoverage: number | null;
  unmappedTruncated: boolean | null;
}

export interface SnapshotDetail extends SnapshotHistoryItem {
  mappingFailures: string[] | null;
  decimalSeparator: string | null;
  priceBasis: string | null;
  sourceFiles: string[] | null;
  comparison: SnapshotComparison;
}
