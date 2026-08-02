import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  CalendarBlank,
  CaretLeft,
  CaretRight,
  CheckCircle,
  ClipboardText,
  Clock,
  Database,
  Gauge,
  Pulse,
  SpinnerGap,
  Star,
} from "@phosphor-icons/react";
import { dashboardRepository } from "./data/dashboardRepository";
import { RoutineLauncher } from "./components/RoutineLauncher";
import type {
  DashboardData,
  Pick,
  ReviewHistoryItem,
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

function initialView(): ViewKey {
  const requested = new URLSearchParams(window.location.search).get("view");
  return navigation.some(({ key }) => key === requested) ? requested as ViewKey : "picks";
}

function fixed(value: number) {
  return value.toFixed(4);
}

function signedFixed(value: number) {
  return `${value > 0 ? "+" : ""}${value.toFixed(4)}`;
}

function percent(value: number, digits = 2) {
  return `${value > 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`;
}

function valueTone(value: number) {
  if (value > 0) return "positive";
  if (value < 0) return "negative";
  return "neutral";
}

function displayDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  return new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric" })
    .format(new Date(`${value}T12:00:00`));
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
          <span><b>Signal</b> {displayDate(data.signalDate)}</span>
        </div>
        <ArrowRight size={18} aria-hidden="true" />
        <div className="date-step">
          <span className="step-number">2</span>
          <span><b>Trade</b> {displayDate(data.tradeDate)}</span>
        </div>
      </div>
      <div className="snapshot-summary">
        <strong>Persisted snapshot #{data.snapshot.id}</strong>
        <span>Imported {data.snapshot.importedAt} from {data.snapshot.source}</span>
      </div>
      <p className="disclaimer">Persisted evidence · Ideas, not execution</p>
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
        <div><dt>Advancer ratio</dt><dd>{data.exposure.advancerRatio === null ? "—" : `${(data.exposure.advancerRatio * 100).toFixed(2)}%`}</dd></div>
        <div><dt>Pick count cap</dt><dd>{data.exposure.pickCountCap}</dd></div>
        <div><dt>Policy</dt><dd>{data.exposure.policy}</dd></div>
      </dl>
    </section>
  );
}

function reviewDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return value.replace(" 2026", "");
  return new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short" })
    .format(new Date(`${value}T12:00:00`));
}

function ReviewPanel({ review, expanded = false, title = "Last review", loading = false }: {
  review: ReviewSummary | null;
  expanded?: boolean;
  title?: string;
  loading?: boolean;
}) {
  if (loading) {
    return (
      <section className={`panel review-panel ${expanded ? "is-expanded" : ""}`} aria-labelledby="review-title" aria-live="polite">
        <h2 id="review-title">{title}</h2>
        <p className="review-loading">Loading persisted review details…</p>
      </section>
    );
  }
  if (!review) {
    return (
      <section className={`panel review-panel ${expanded ? "is-expanded" : ""}`} aria-labelledby="review-title">
        <h2 id="review-title">{title}</h2>
        <p>No persisted review is available yet.</p>
      </section>
    );
  }
  return (
    <section className={`panel review-panel ${expanded ? "is-expanded" : ""}`} aria-labelledby="review-title">
      <h2 id="review-title">{title}</h2>
      <div className="review-dates">
        <strong>Review #{review.id}</strong>
        <span>Signal {reviewDate(review.signalDate)}</span>
        <span>Review {reviewDate(review.reviewDate)}</span>
      </div>
      <dl className="review-metrics">
        <div><dt>Average return</dt><dd className={valueTone(review.averageReturn)}>{percent(review.averageReturn)}</dd></div>
        <div><dt>Win rate</dt><dd className="neutral">{(review.winRate * 100).toFixed(0)}%</dd></div>
        <div><dt>Wins</dt><dd className="neutral">{review.wins} of {review.pickCount}</dd></div>
      </dl>
      <div className="threshold">
        <span>Minimum win threshold</span>
        <strong>+{(review.minimumWinReturn * 100).toFixed(0)}%</strong>
      </div>
      <h3>Reviewed outcomes</h3>
      {review.outcomes.length === 0 ? (
        <p className="review-empty-outcomes">No pick outcomes were recorded for this review.</p>
      ) : (
        <table className="outcome-table" aria-label="Reviewed pick outcomes">
          <thead>
            <tr><th scope="col">Pick</th><th scope="col">Return</th><th scope="col">Result</th></tr>
          </thead>
          <tbody>
            {review.outcomes.map((outcome) => (
              <tr key={outcome.ticker}>
                <td><strong>{outcome.ticker}</strong></td>
                <td className={valueTone(outcome.returnPct)}>{percent(outcome.returnPct)}</td>
                <td className={outcome.won ? "positive" : "negative"}>{outcome.won ? "Win" : "Loss"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function ReviewHistoryList({ reviews, selectedId, onSelect }: {
  reviews: ReviewHistoryItem[];
  selectedId: number | null;
  onSelect: (reviewId: number) => void;
}) {
  const listRef = useRef<HTMLDivElement | null>(null);
  const selectedRowRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    const list = listRef.current;
    const row = selectedRowRef.current;
    if (!list || !row) return;
    const listRect = list.getBoundingClientRect();
    const rowRect = row.getBoundingClientRect();
    if (rowRect.top < listRect.top || rowRect.bottom > listRect.bottom) {
      list.scrollTop += rowRect.top - listRect.top - (listRect.height - rowRect.height) / 2;
    }
  }, [selectedId]);

  return (
    <section className="panel review-history-panel" aria-labelledby="review-history-title">
      <h2 id="review-history-title">Review history <span>• {reviews.length}</span></h2>
      <div className="review-history-columns" aria-hidden="true"><span>Signal date</span><span>Avg</span><span>Wins</span></div>
      {reviews.length === 0 ? (
        <p className="review-history-empty">No persisted review history is available yet.</p>
      ) : (
        <div className="review-history-list" ref={listRef} aria-label="Previous pick reviews">
          {reviews.map((review) => (
            <button
              type="button"
              className={`review-history-row ${selectedId === review.id ? "is-selected" : ""}`}
              key={review.id}
              ref={selectedId === review.id ? selectedRowRef : undefined}
              onClick={() => onSelect(review.id)}
              aria-current={selectedId === review.id ? "date" : undefined}
              aria-label={`Review ${review.id}, signal ${review.signalDate}, average return ${percent(review.averageReturn)}, ${review.wins} wins out of ${review.pickCount}`}
            >
              <span className="history-row-date">
                <strong>{reviewDate(review.signalDate)}</strong>
                <small>Reviewed {reviewDate(review.reviewDate)}</small>
              </span>
              <span className={`${valueTone(review.averageReturn)} history-return`}>{percent(review.averageReturn)}</span>
              <span className="history-wins">{review.wins}/{review.pickCount}<small>wins</small></span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function ReviewNavigator({ reviews, selectedId, loading, onSelect }: {
  reviews: ReviewHistoryItem[];
  selectedId: number | null;
  loading: boolean;
  onSelect: (reviewId: number) => void;
}) {
  const selectedIndex = reviews.findIndex((review) => review.id === selectedId);
  const newerReview = selectedIndex > 0 ? reviews[selectedIndex - 1] : null;
  const olderReview = selectedIndex >= 0 && selectedIndex < reviews.length - 1 ? reviews[selectedIndex + 1] : null;
  const position = selectedIndex >= 0 ? selectedIndex + 1 : 0;

  return (
    <section className="panel review-navigator" aria-labelledby="review-navigator-title">
      <div className="review-navigator-copy">
        <p className="eyebrow">Browse history</p>
        <h2 id="review-navigator-title">Choose a signal date</h2>
        <p>{reviews.length === 0 ? "No persisted reviews" : `${position} of ${reviews.length} · newest first`}</p>
      </div>
      <div className="review-navigator-controls">
        <button
          type="button"
          className="review-step-button"
          disabled={loading || !newerReview}
          onClick={() => newerReview && onSelect(newerReview.id)}
          aria-label={newerReview ? `Newer review, signal ${newerReview.signalDate}` : "No newer review"}
        >
          <CaretLeft size={18} aria-hidden="true" /> Newer
        </button>
        <label className="review-date-control">
          <span>Signal date</span>
          <select
            value={selectedId ?? ""}
            disabled={loading || reviews.length === 0}
            onChange={(event) => onSelect(Number(event.target.value))}
          >
            {reviews.map((review) => (
              <option value={review.id} key={review.id}>
                {displayDate(review.signalDate)} · {percent(review.averageReturn)} avg · {review.wins}/{review.pickCount} wins
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="review-step-button"
          disabled={loading || !olderReview}
          onClick={() => olderReview && onSelect(olderReview.id)}
          aria-label={olderReview ? `Older review, signal ${olderReview.signalDate}` : "No older review"}
        >
          Older <CaretRight size={18} aria-hidden="true" />
        </button>
      </div>
    </section>
  );
}

function RunTimeline({ data }: { data: DashboardData }) {
  return (
    <section className="panel run-timeline" aria-labelledby="timeline-title">
      <h2 id="timeline-title"><Clock size={18} aria-hidden="true" /> Run timeline</h2>
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
        <span><strong>Previous close → latest</strong><br />{displayDate(data.signalDate)}</span>
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
        <p>Reading the latest persisted SQLite snapshot.</p>
        <div className="skeleton-lines" aria-hidden="true"><span /><span /><span /></div>
        <button type="button" className="secondary-action" onClick={onRetry}>Retry</button>
      </section>
    );
  }
  return (
    <section className="panel status-view" aria-live="polite">
      <Database size={32} aria-hidden="true" />
      <h2>No persisted ideas for this signal date</h2>
      <p>Import the four daily CSV inputs and run the persisted routine before reviewing picks.</p>
      <button type="button" className="secondary-action" onClick={onRetry}>Retry</button>
    </section>
  );
}

function OverviewView({ data, onNavigate }: { data: DashboardData; onNavigate: (view: ViewKey) => void }) {
  return (
    <div className="overview-view">
      <section className="panel overview-hero">
        <p className="eyebrow">Target trade · {data.tradeDate}</p>
        <h2>{data.picks.length} persisted intraday ideas</h2>
        <p>Score-ranked from the {displayDate(data.signalDate)} snapshot. Exposure policy: {data.exposure.policy}.</p>
        <button type="button" className="primary-action" onClick={() => onNavigate("picks")}>Inspect today's picks</button>
      </section>
      <ExposurePanel data={data} />
      <ReviewPanel review={data.review} />
      <RunTimeline data={data} />
    </div>
  );
}

function ReviewsView({
  reviews,
  selectedReview,
  selectedReviewId,
  loading,
  error,
  onSelect,
}: {
  reviews: ReviewHistoryItem[];
  selectedReview: ReviewSummary | null;
  selectedReviewId: number | null;
  loading: boolean;
  error: string | null;
  onSelect: (reviewId: number) => void;
}) {
  return (
    <div className="reviews-view">
      <div className="view-intro"><p className="eyebrow">Persisted performance</p><h2>Review past picks</h2><p>Move through signal dates, then inspect the recorded return and result for every pick.</p></div>
      <ReviewNavigator reviews={reviews} selectedId={selectedReviewId} loading={loading} onSelect={onSelect} />
      <div className="review-history-layout">
        <ReviewHistoryList reviews={reviews} selectedId={selectedReviewId} onSelect={onSelect} />
        <div className="review-detail" id="review-detail" aria-live="polite" aria-busy={loading}>
          {error && <p className="review-error" role="alert">{error}</p>}
          <ReviewPanel
            review={selectedReview}
            title={selectedReview ? `Picks from ${displayDate(selectedReview.signalDate)}` : "Review details"}
            expanded
            loading={loading}
          />
        </div>
      </div>
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

function RunsView({ data, reload }: {
  data: DashboardData;
  reload: () => Promise<void>;
}) {
  return (
    <div className="runs-view">
      <RoutineLauncher onComplete={reload} />
      <section className="panel run-summary-panel">
        <p className="eyebrow">Displayed persisted evidence</p>
        <h2>Snapshot #{data.snapshot.id}</h2>
        <dl className="compact-list">
          <div><dt>Imported</dt><dd>{data.snapshot.importedAt}</dd></div>
          <div><dt>Source</dt><dd>{data.snapshot.source}</dd></div>
          <div><dt>Status</dt><dd><CheckCircle size={17} aria-hidden="true" /> {data.snapshot.status}</dd></div>
          <div><dt>Price basis</dt><dd>previous close → latest</dd></div>
        </dl>
      </section>
      <RunTimeline data={data} />
    </div>
  );
}

export function App() {
  const { data, status, reload } = useDashboard(dashboardRepository);
  const [activeView, setActiveView] = useState<ViewKey>(initialView);
  const [selectedTicker, setSelectedTicker] = useState("AKSEN");
  const [selectedReviewId, setSelectedReviewId] = useState<number | null>(null);
  const [selectedReview, setSelectedReview] = useState<ReviewSummary | null>(null);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const reviewRequestId = useRef(0);

  useEffect(() => {
    reviewRequestId.current += 1;
    setReviewLoading(false);
    setSelectedReviewId(data?.review?.id ?? null);
    setSelectedReview(data?.review ?? null);
    setReviewError(null);
  }, [data]);

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

  const revealReviewDetail = () => {
    if (!window.matchMedia("(max-width: 820px)").matches) return;
    window.setTimeout(() => document.getElementById("review-detail")?.scrollIntoView({
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
      block: "start",
    }), 0);
  };

  const selectReview = async (reviewId: number) => {
    if (selectedReview?.id === reviewId) {
      revealReviewDetail();
      return;
    }
    const requestId = ++reviewRequestId.current;
    setSelectedReviewId(reviewId);
    setReviewError(null);
    if (data?.review?.id === reviewId) {
      setSelectedReview(data.review);
      setReviewLoading(false);
      revealReviewDetail();
      return;
    }
    setReviewLoading(true);
    revealReviewDetail();
    try {
      const review = await dashboardRepository.loadReview(reviewId);
      if (requestId === reviewRequestId.current) setSelectedReview(review);
    } catch (error) {
      if (requestId === reviewRequestId.current) {
        setSelectedReview(null);
        setReviewError(error instanceof Error ? error.message : "The selected review could not be loaded.");
      }
    } finally {
      if (requestId === reviewRequestId.current) setReviewLoading(false);
    }
  };

  const navigate = (view: ViewKey) => {
    setActiveView(view);
    const url = new URL(window.location.href);
    if (view === "picks") {
      url.searchParams.delete("view");
    } else {
      url.searchParams.set("view", view);
    }
    window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
  };

  if (!data) {
    return (
      <div className="app-shell boot-shell">
        <Sidebar activeView={activeView} onNavigate={navigate} />
        <main className="workspace"><StatusView kind={status === "error" ? "empty" : "loading"} onRetry={() => void reload()} /></main>
      </div>
    );
  }

  const renderView = () => {
    if (!selectedPick) return null;

    if (activeView === "overview") return <OverviewView data={data} onNavigate={navigate} />;
    if (activeView === "reviews") {
      return (
        <ReviewsView
          reviews={data.reviewHistory}
          selectedReview={selectedReview}
          selectedReviewId={selectedReviewId}
          loading={reviewLoading}
          error={reviewError}
          onSelect={(reviewId) => void selectReview(reviewId)}
        />
      );
    }
    if (activeView === "diagnostics") return <DiagnosticsView picks={data.picks} selectedPick={selectedPick} onSelect={selectPick} />;
    if (activeView === "runs") return <RunsView data={data} reload={reload} />;

    return (
      <div className="dashboard-view">
        <div className="evidence-grid">
          <PickList picks={data.picks} selectedTicker={selectedPick.ticker} onSelect={selectPick} />
          <EvidencePanel pick={selectedPick} onOpenDiagnostics={() => navigate("diagnostics")} />
          <div className="right-stack"><ExposurePanel data={data} /><ReviewPanel review={data.review} /></div>
        </div>
        <RunTimeline data={data} />
      </div>
    );
  };

  return (
    <div className="app-shell">
      <Sidebar activeView={activeView} onNavigate={navigate} />
      <main className="workspace">
        <SessionHeader data={data} />
        {renderView()}
      </main>
    </div>
  );
}
