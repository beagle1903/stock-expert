import { useEffect, useState } from "react";
import {
  ArrowClockwise,
  ArrowRight,
  CheckCircle,
  FileCsv,
  Play,
  ShieldCheck,
  SpinnerGap,
  WarningCircle,
  XCircle,
} from "@phosphor-icons/react";
import { routineRepository } from "../data/routineRepository";
import type { RoutinePreview, RoutineRunResult } from "../domain/routine";

function localIsoDate() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function displayDate(value: string) {
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(`${value}T12:00:00`));
}

function displayTimestamp(value: string | null) {
  if (!value) return "Not available";
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function inputStatusLabel(status: string) {
  if (status === "ready") return "Ready";
  if (status === "missing") return "Missing";
  if (status === "empty") return "Empty";
  return "Stale";
}

export function RoutineLauncher({ onComplete }: { onComplete?: () => void | Promise<void> }) {
  const [requestedDate, setRequestedDate] = useState(localIsoDate);
  const [refreshKey, setRefreshKey] = useState(0);
  const [preview, setPreview] = useState<RoutinePreview | null>(null);
  const [previewStatus, setPreviewStatus] = useState<"loading" | "ready" | "error">("loading");
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [confirmationOpen, setConfirmationOpen] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [runStatus, setRunStatus] = useState<"idle" | "running" | "success" | "error">("idle");
  const [runError, setRunError] = useState<string | null>(null);
  const [result, setResult] = useState<RoutineRunResult | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setPreviewStatus("loading");
      setPreviewError(null);
      setConfirmationOpen(false);
      setConfirmed(false);
      setRunStatus("idle");
      setResult(null);
      void routineRepository.preview(requestedDate, controller.signal)
        .then((value) => {
          setPreview(value);
          setPreviewStatus("ready");
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted) return;
          setPreview(null);
          setPreviewError(error instanceof Error ? error.message : "Routine preview failed.");
          setPreviewStatus("error");
        });
    }, 180);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [requestedDate, refreshKey]);

  const runRoutine = async () => {
    if (!preview || !confirmed) return;
    setRunStatus("running");
    setRunError(null);
    try {
      const nextResult = await routineRepository.run({
        requestedSignalDate: requestedDate,
        confirmationToken: preview.confirmationToken,
        confirmed: true,
      });
      setResult(nextResult);
      setRunStatus("success");
      setConfirmationOpen(false);
      setConfirmed(false);
      void Promise.resolve().then(() => onComplete?.()).catch(() => undefined);
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "Routine failed.");
      setRunStatus("error");
    }
  };

  return (
    <section className="panel routine-launcher" aria-labelledby="routine-launcher-title">
      <div className="routine-launcher-heading">
        <div>
          <p className="eyebrow">Persisted operator action</p>
          <h2 id="routine-launcher-title">Run routine</h2>
          <p>Import the four live CSV files, persist picks, review the prior session, and report diagnostics.</p>
        </div>
        <label className="date-control">
          <span>Requested signal date</span>
          <input
            type="date"
            value={requestedDate}
            max={localIsoDate()}
            onChange={(event) => setRequestedDate(event.target.value)}
            disabled={runStatus === "running"}
          />
        </label>
      </div>

      {previewStatus === "loading" && (
        <div className="routine-loading" role="status">
          <SpinnerGap className="spin" size={22} aria-hidden="true" /> Checking calendar and CSV inputs…
        </div>
      )}

      {previewStatus === "error" && (
        <div className="routine-message routine-message-error" role="alert">
          <XCircle size={21} aria-hidden="true" />
          <span><strong>Routine API unavailable.</strong> {previewError}</span>
          <button type="button" onClick={() => setRefreshKey((value) => value + 1)}>Retry</button>
        </div>
      )}

      {preview && previewStatus === "ready" && (
        <>
          <div className="routine-route" aria-label="Resolved routine date route">
            {!preview.requestedWasTradingSession && (
              <div><span>Requested</span><strong>{displayDate(preview.requestedSignalDate)}</strong><small>Market closed</small></div>
            )}
            <div><span>Signal data</span><strong>{displayDate(preview.resolvedSignalDate)}</strong><small>Resolved session</small></div>
            <ArrowRight size={18} aria-hidden="true" />
            <div><span>Target trade</span><strong>{displayDate(preview.targetTradeDate)}</strong><small>Next open session</small></div>
            <div className="policy-summary"><span>Policy</span><strong>{preview.marketContext.selection_policy.replaceAll("_", " ")}</strong><small>Repository calendar</small></div>
          </div>

          <div className="routine-file-grid" aria-label="Routine input readiness">
            {preview.files.map((file) => (
              <div className={`routine-file routine-file-${file.status}`} key={file.name}>
                <FileCsv size={22} aria-hidden="true" />
                <span><strong>{file.name}</strong><small>{displayTimestamp(file.modifiedAt)}</small></span>
                <b>{inputStatusLabel(file.status)}</b>
              </div>
            ))}
          </div>

          {preview.blockingIssues.length > 0 && (
            <div className="routine-message routine-message-error" role="alert">
              <XCircle size={21} aria-hidden="true" />
              <span><strong>Not ready.</strong> {preview.blockingIssues.join(" ")}</span>
            </div>
          )}

          <div className="routine-message routine-message-warning">
            <WarningCircle size={21} aria-hidden="true" />
            <span>{preview.warnings.join(" ")}</span>
          </div>

          {confirmationOpen && preview.ready && runStatus !== "running" && (
            <div className="routine-confirmation">
              <ShieldCheck size={28} aria-hidden="true" />
              <div>
                <strong>Confirm persisted routine</strong>
                <p>
                  Signal {displayDate(preview.resolvedSignalDate)} → trade {displayDate(preview.targetTradeDate)}.
                  This writes a new snapshot, picks, and any eligible review to branch-isolated SQLite.
                </p>
                <label>
                  <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
                  I confirm the four CSV files contain data for {displayDate(preview.resolvedSignalDate)}.
                </label>
              </div>
            </div>
          )}

          {runStatus === "running" && (
            <div className="routine-progress" role="status" aria-live="polite">
              <SpinnerGap className="spin" size={25} aria-hidden="true" />
              <div><strong>Routine is running</strong><span>Importing CSVs → persisting snapshot and picks → reviewing prior session → diagnostics</span></div>
            </div>
          )}

          {runStatus === "error" && (
            <div className="routine-message routine-message-error" role="alert">
              <XCircle size={21} aria-hidden="true" />
              <span><strong>Routine failed.</strong> {runError}</span>
            </div>
          )}

          {runStatus === "success" && result && (
            <div className="routine-result" role="status">
              <CheckCircle size={27} weight="fill" aria-hidden="true" />
              <div><strong>Routine persisted</strong><span>Snapshot #{result.snapshotId ?? "—"} · {result.pickCount} picks · Review {result.reviewRunId ? `#${result.reviewRunId}` : "not created"}</span></div>
              <small>Completed {displayTimestamp(result.completedAt)}</small>
            </div>
          )}

          <div className="routine-actions">
            <button className="secondary-action" type="button" onClick={() => setRefreshKey((value) => value + 1)} disabled={runStatus === "running"}>
              <ArrowClockwise size={18} aria-hidden="true" /> Refresh checks
            </button>
            {!confirmationOpen ? (
              <button className="primary-action routine-run-button" type="button" disabled={!preview.ready || runStatus === "running"} onClick={() => setConfirmationOpen(true)}>
                <Play size={18} weight="fill" aria-hidden="true" /> Review & run
              </button>
            ) : (
              <button className="primary-action routine-run-button" type="button" disabled={!confirmed || runStatus === "running"} onClick={() => void runRoutine()}>
                <Play size={18} weight="fill" aria-hidden="true" /> Confirm and run
              </button>
            )}
          </div>
        </>
      )}
    </section>
  );
}
