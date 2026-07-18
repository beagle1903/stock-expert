import { useMemo, useState } from "react";
import {
  ArrowRight,
  CalendarBlank,
  CheckCircle,
  ClipboardText,
  Clock,
  Database,
  Gauge,
  Pulse,
  SpinnerGap,
  Star,
  WarningCircle,
} from "@phosphor-icons/react";
import { mockDashboardRepository } from "./data/dashboardRepository";
import { RoutineLauncher } from "./components/RoutineLauncher";
import type {
  DashboardData,
  Pick,
  PreviewState,
  ReviewSummary,
  ViewKey,
} from "./domain/dashboard";
import { useDashboard } from "./hooks/useDashboard";

const navigation = [
  { key: "overview", label: "Overview", icon: Gauge },
  { key: "picks", label: "Today's Picks", icon: Star },
  { key: "reviews", label: "Reviews", icon: ClipboardText },
  { key: "diagnostics", label: "Diagnostics", icon: Pulse },
  { key: "runs", label: "Data & Runs", icon: Database },
] as const;

const previewStates: PreviewState[] = ["loaded", "loading", "empty", "error"];

function fixed(value: number) {
  return value.toFixed(4);
}

function signedFixed(value: number) {
  return `${value > 0 ? "+" : ""}${value.toFixed(4)}`;
}

function percent(value: number, digits = 2) {
  return `${value > 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`;
}

function Sidebar({ activeView, onNavigate }: { activeView: ViewKey; onNavigate: (view: ViewKey) => void }) {
  return (
    <aside className="sidebar" aria-label="Primary navigation">
      <div className="brand">Stock Expert</div>
      <nav className="nav-list">
        {navigation.map(({ key, label, icon: Icon }) => (
          <button
            className={`nav-item ${activeView === key ? "is-active" : ""}`}
            type="button"
            key={key}
            onClick={() => onNavigate(key)}
            aria-current={activeView === key ? "page" : undefined}
          >
            <Icon size={30} weight="regular" aria-hidden="true" />
            <span>{label}</span>
          </button>
        ))}
      </nav>
    </aside>
  );
}

function SessionHeader({ data }: { data: DashboardData }) {
  return (
    <header className="session-header">
      <h1>Evidence Console</h1>
      <div className="date-route" aria-label={`Signal ${data.signalDate}, target trade ${data.tradeDate}`}>
        <div className="date-step">
          <span className="step-number">1</span>
          <span><b>Signal</b> {data.signalDate}</span>
        </div>
        <ArrowRight size={18} aria-hidden="true" />
        <div className="date-step">
          <span className="step-number">2</span>
          <span><b>Trade</b> {data.tradeDate}</span>
        </div>
      </div>
      <div className="snapshot-summary">
        <strong>Sample snapshot #{data.snapshot.id}</strong>
        <span>Imported {data.snapshot.importedAt} from {data.snapshot.source}</span>
      </div>
      <p className="disclaimer">Sample evidence · Ideas, not execution</p>
    </header>
  );
}

function PickList({ picks, selectedTicker, onSelect }: {
  picks: Pick[];
  selectedTicker: string;
  onSelect: (ticker: string) => void;
}) {
  return (
    <section className="panel pick-panel" aria-labelledby="pick-list-title">
      <h2 id="pick-list-title">Today <span>• {picks.length} persisted ideas</span></h2>
      <div className="pick-head" aria-hidden="true">
        <span>Rank</span><span>Ticker</span><span>Score</span><span>Risk</span>
      </div>
      <div className="pick-list" role="listbox" aria-label="Persisted pick list">
        {picks.map((pick) => (
          <button
            type="button"
            className={`pick-row ${selectedTicker === pick.ticker ? "is-selected" : ""}`}
            key={pick.ticker}
            onClick={() => onSelect(pick.ticker)}
            role="option"
            aria-selected={selectedTicker === pick.ticker}
          >
            <span className="rank">{pick.rank}</span>
            <strong>{pick.ticker}</strong>
            <span className="numeric">{fixed(pick.score)}</span>
            <span className={`risk risk-${pick.risk}`}>{pick.risk}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

function EvidencePanel({ pick, onOpenDiagnostics }: { pick: Pick; onOpenDiagnostics?: () => void }) {
  const fields = [
    ["Momentum", fixed(pick.signals.momentum)],
    ["Volume", fixed(pick.signals.volume)],
    ["Technical", signedFixed(pick.signals.technical)],
    ["Fundamental", signedFixed(pick.signals.fundamental)],
    ["Quality", signedFixed(pick.signals.quality)],
    ["Setup penalty", fixed(pick.signals.setupPenalty)],
    ["MA trend", fixed(pick.signals.maTrend)],
    ["Liquidity", fixed(pick.signals.liquidity)],
  ];

  return (
    <section className="panel evidence-panel" id="evidence-panel" aria-labelledby="evidence-title">
      <h2 id="evidence-title">{pick.ticker} evidence</h2>
      <div className="tag-row">
        <span className="tag tag-blue">{pick.selectionBucket}</span>
        <span className="tag tag-purple">{pick.horizon}</span>
      </div>
      <h3>Signal and adjustment values</h3>
      <dl className="metric-table">
        <div className="metric-head"><dt>Field</dt><dd>Value</dd></div>
        {fields.map(([label, value]) => (
          <div key={label}><dt>{label}</dt><dd>{value}</dd></div>
        ))}
        <div className="metric-summary"><dt>Total boost</dt><dd>{signedFixed(pick.signals.totalBoost)}</dd></div>
        <div className="metric-final"><dt>Net adjustment</dt><dd>{signedFixed(pick.signals.netAdjustment)}</dd></div>
      </dl>
      {onOpenDiagnostics && (
        <button className="primary-action" type="button" onClick={onOpenDiagnostics}>
          Open full diagnostics
        </button>
      )}
    </section>
  );
}

function ExposurePanel({ data }: { data: DashboardData }) {
  return (
    <section className="panel exposure-panel" aria-labelledby="exposure-title">
      <h2 id="exposure-title">Exposure policy</h2>
      <dl className="compact-list">
        <div><dt>Universe</dt><dd>{data.exposure.universeCount}</dd></div>
        <div><dt>Advancer ratio</dt><dd>{(data.exposure.advancerRatio * 100).toFixed(2)}%</dd></div>
        <div><dt>Pick count cap</dt><dd>{data.exposure.pickCountCap}</dd></div>
        <div><dt>Policy</dt><dd>{data.exposure.policy}</dd></div>
      </dl>
    </section>
  );
}

function ReviewPanel({ review, expanded = false }: { review: ReviewSummary; expanded?: boolean }) {
  return (
    <section className={`panel review-panel ${expanded ? "is-expanded" : ""}`} aria-labelledby="review-title">
      <h2 id="review-title">Last review</h2>
      <div className="review-dates">
        <strong>Review #{review.id}</strong>
        <span>Signal {review.signalDate.replace(" 2026", "")}</span>
        <span>Review {review.reviewDate.replace(" 2026", "")}</span>
      </div>
      <dl className="review-metrics">
        <div><dt>Average return</dt><dd>{percent(review.averageReturn)}</dd></div>
        <div><dt>Win rate</dt><dd>{(review.winRate * 100).toFixed(0)}%</dd></div>
        <div><dt>Wins</dt><dd>{review.wins} of {review.pickCount}</dd></div>
      </dl>
      <div className="threshold">
        <span>Minimum win threshold</span>
        <strong>+{(review.minimumWinReturn * 100).toFixed(0)}%</strong>
      </div>
      <h3>Reviewed outcomes</h3>
      <div className="outcome-list">
        {review.outcomes.map((outcome) => (
          <div key={outcome.ticker}>
            <strong>{outcome.ticker}</strong>
            <span className={outcome.returnPct < 0 ? "negative" : "positive"}>{percent(outcome.returnPct)}</span>
            <span className={outcome.won ? "positive" : "negative"}>{outcome.won ? "win" : "loss"}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function RunTimeline({ data, sample = false }: { data: DashboardData; sample?: boolean }) {
  return (
    <section className="panel run-timeline" aria-labelledby="timeline-title">
      <h2 id="timeline-title"><Clock size={18} aria-hidden="true" /> {sample ? "Sample run timeline" : "Run timeline"}</h2>
      <ol>
        {data.runSteps.map((step) => (
          <li key={step.id}>
            <span className="timeline-number">{step.id}</span>
            <strong>{step.label}</strong>
            <span>{step.detail}</span>
          </li>
        ))}
      </ol>
      <div className="price-basis">
        <CalendarBlank size={25} aria-hidden="true" />
        <span><strong>Previous close → latest</strong><br />16 Jul 2026 → 16 Jul 2026</span>
      </div>
    </section>
  );
}

function StatusView({ kind, onRetry }: { kind: "loading" | "empty"; onRetry: () => void }) {
  if (kind === "loading") {
    return (
      <section className="panel status-view" aria-live="polite">
        <SpinnerGap size={32} className="spin" aria-hidden="true" />
        <h2>Loading persisted evidence</h2>
        <p>Reading the typed dashboard snapshot.</p>
        <div className="skeleton-lines" aria-hidden="true"><span /><span /><span /></div>
        <button type="button" className="secondary-action" onClick={onRetry}>Return to loaded mock</button>
      </section>
    );
  }
  return (
    <section className="panel status-view" aria-live="polite">
      <Database size={32} aria-hidden="true" />
      <h2>No persisted ideas for this signal date</h2>
      <p>Import the four daily CSV inputs and run the persisted routine before reviewing picks.</p>
      <button type="button" className="secondary-action" onClick={onRetry}>Return to loaded mock</button>
    </section>
  );
}

function ErrorBanner({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div className="error-banner" role="alert">
      <WarningCircle size={22} aria-hidden="true" />
      <span><strong>Refresh failed.</strong> Showing the last persisted Snapshot #100 from 16 Jul at 18:34 TRT.</span>
      <button type="button" onClick={onDismiss}>Dismiss</button>
    </div>
  );
}

function OverviewView({ data, onNavigate }: { data: DashboardData; onNavigate: (view: ViewKey) => void }) {
  return (
    <div className="overview-view">
      <section className="panel overview-hero">
        <p className="eyebrow">Target trade · {data.tradeDate}</p>
        <h2>{data.picks.length} persisted intraday ideas</h2>
        <p>Score-ranked from the {data.signalDate} snapshot. Market exposure policy remains normal.</p>
        <button type="button" className="primary-action" onClick={() => onNavigate("picks")}>Inspect today's picks</button>
      </section>
      <ExposurePanel data={data} />
      <ReviewPanel review={data.review} />
      <RunTimeline data={data} />
    </div>
  );
}

function ReviewsView({ review }: { review: ReviewSummary }) {
  return (
    <div className="single-view">
      <div className="view-intro"><p className="eyebrow">Persisted performance</p><h2>Review #{review.id}</h2><p>Observed outcomes only; the minimum win threshold is +4%.</p></div>
      <ReviewPanel review={review} expanded />
    </div>
  );
}

function DiagnosticsView({ picks, selectedPick, onSelect }: { picks: Pick[]; selectedPick: Pick; onSelect: (ticker: string) => void }) {
  return (
    <div className="diagnostics-view">
      <div className="view-intro"><p className="eyebrow">Point-in-time evidence</p><h2>Pick diagnostics</h2><p>Normalized signal values and bounded adjustments from the selected signal date.</p></div>
      <PickList picks={picks} selectedTicker={selectedPick.ticker} onSelect={onSelect} />
      <EvidencePanel pick={selectedPick} />
    </div>
  );
}

function RunsView({ data, previewState, onPreviewState }: {
  data: DashboardData;
  previewState: PreviewState;
  onPreviewState: (state: PreviewState) => void;
}) {
  return (
    <div className="runs-view">
      <RoutineLauncher />
      <section className="panel run-summary-panel">
        <p className="eyebrow">Displayed sample evidence</p>
        <h2>Sample snapshot #{data.snapshot.id}</h2>
        <dl className="compact-list">
          <div><dt>Imported</dt><dd>{data.snapshot.importedAt}</dd></div>
          <div><dt>Source</dt><dd>{data.snapshot.source}</dd></div>
          <div><dt>Status</dt><dd><CheckCircle size={17} aria-hidden="true" /> {data.snapshot.status}</dd></div>
          <div><dt>Price basis</dt><dd>previous close → latest</dd></div>
        </dl>
      </section>
      <section className="panel state-preview-panel">
        <p className="eyebrow">Presentation states</p>
        <h2>Mock state preview</h2>
        <p>These controls exercise UI-only states; they never mutate SQLite or strategy behavior.</p>
        <div className="state-buttons" role="group" aria-label="Preview dashboard state">
          {previewStates.map((state) => (
            <button
              key={state}
              type="button"
              className={previewState === state ? "is-active" : ""}
              onClick={() => onPreviewState(state)}
            >
              {state}
            </button>
          ))}
        </div>
      </section>
      <RunTimeline data={data} sample />
    </div>
  );
}

export function App() {
  const { data, status, reload } = useDashboard(mockDashboardRepository);
  const [activeView, setActiveView] = useState<ViewKey>("picks");
  const [selectedTicker, setSelectedTicker] = useState("AKSEN");
  const [previewState, setPreviewState] = useState<PreviewState>("loaded");

  const selectedPick = useMemo(
    () => data?.picks.find((pick) => pick.ticker === selectedTicker) ?? data?.picks[0],
    [data, selectedTicker],
  );

  const selectPick = (ticker: string) => {
    setSelectedTicker(ticker);
    if (window.matchMedia("(max-width: 760px)").matches) {
      window.setTimeout(() => document.getElementById("evidence-panel")?.scrollIntoView({ behavior: "smooth" }), 0);
    }
  };

  if (!data) {
    return (
      <div className="app-shell boot-shell">
        <Sidebar activeView={activeView} onNavigate={setActiveView} />
        <main className="workspace"><StatusView kind={status === "error" ? "empty" : "loading"} onRetry={() => void reload()} /></main>
      </div>
    );
  }

  const renderView = () => {
    if (previewState === "loading") return <StatusView kind="loading" onRetry={() => setPreviewState("loaded")} />;
    if (previewState === "empty") return <StatusView kind="empty" onRetry={() => setPreviewState("loaded")} />;
    if (!selectedPick) return null;

    if (activeView === "overview") return <OverviewView data={data} onNavigate={setActiveView} />;
    if (activeView === "reviews") return <ReviewsView review={data.review} />;
    if (activeView === "diagnostics") return <DiagnosticsView picks={data.picks} selectedPick={selectedPick} onSelect={selectPick} />;
    if (activeView === "runs") return <RunsView data={data} previewState={previewState} onPreviewState={setPreviewState} />;

    return (
      <div className="dashboard-view">
        <div className="evidence-grid">
          <PickList picks={data.picks} selectedTicker={selectedPick.ticker} onSelect={selectPick} />
          <EvidencePanel pick={selectedPick} onOpenDiagnostics={() => setActiveView("diagnostics")} />
          <div className="right-stack"><ExposurePanel data={data} /><ReviewPanel review={data.review} /></div>
        </div>
        <RunTimeline data={data} />
      </div>
    );
  };

  return (
    <div className="app-shell">
      <Sidebar activeView={activeView} onNavigate={setActiveView} />
      <main className="workspace">
        <SessionHeader data={data} />
        {previewState === "error" && <ErrorBanner onDismiss={() => setPreviewState("loaded")} />}
        {renderView()}
      </main>
    </div>
  );
}
