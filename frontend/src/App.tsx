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
import { strategyEvidenceRepository } from "./data/strategyEvidenceRepository";
import { playbackNotices } from "./data/strategyPlaybackViewModel.mjs";
import {
  appContentMode,
  evidenceDisplayState,
  evidenceWindowOptions,
  findStrategySummary,
} from "./data/strategyEvidenceViewModel.mjs";
import { RoutineLauncher } from "./components/RoutineLauncher";
import type {
  DashboardData,
  MissedMover,
  MissedMoverClassification,
  Pick,
  ReviewHistoryItem,
  ReviewSummary,
  ViewKey,
} from "./domain/dashboard";
import type { EvidenceWindow, StrategyEvidence } from "./domain/strategyEvidence";
import type { StrategyPlayback } from "./domain/strategyPlayback";
import { useDashboard } from "./hooks/useDashboard";
import { useStrategyEvidence } from "./hooks/useStrategyEvidence";

const navigation = [
  { key: "overview", label: "Overview", icon: Gauge },
  { key: "picks", label: "Today's Picks", icon: Star },
  { key: "reviews", label: "Reviews", icon: ClipboardText },
  { key: "diagnostics", label: "Strategy Lab", icon: Pulse },
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

function ratioPercent(value: number, digits = 1) {
  return `${(value * 100).toFixed(digits)}%`;
}

function label(value: string) {
  return value.replaceAll("_", " ");
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

function StrategyPlaybackPanel({ playback, loading }: {
  playback: StrategyPlayback | null;
  loading: boolean;
}) {
  if (loading) {
    return (
      <section className="panel playback-panel playback-loading" aria-live="polite">
        <SpinnerGap className="spin" size={22} aria-hidden="true" /> Loading point-in-time playback…
      </section>
    );
  }
  if (!playback) return null;

  const notices = playbackNotices(playback);
  return (
    <section className="panel playback-panel" aria-labelledby="playback-title">
      <div className="playback-heading">
        <div><p className="eyebrow">Point-in-time evidence</p><h2 id="playback-title">Historical strategy playback</h2></div>
        <span className={`evidence-status evidence-status-${playback.signal.status}`}>{playback.signal.status}</span>
      </div>
      <div className="playback-route" aria-label="Playback dates">
        <div><span>Signal snapshot</span><strong>{displayDate(playback.signal.signalDate)}</strong><small>{playback.signal.snapshotId ? `#${playback.signal.snapshotId}` : "Not captured"}</small></div>
        <ArrowRight size={20} aria-hidden="true" />
        <div><span>Review outcome</span><strong>{displayDate(playback.signal.targetTradeDate)}</strong><small>Review #{playback.review.id}</small></div>
      </div>
      <dl className="playback-context">
        <div><dt>Strategy</dt><dd>{label(playback.strategy.selectedStrategy)}</dd></div>
        <div><dt>Version</dt><dd>{playback.strategy.version}</dd></div>
        <div><dt>Universe</dt><dd>{playback.signal.status === "available" ? playback.signal.universeCount : "—"}</dd></div>
        <div><dt>Advancers</dt><dd>{playback.signal.advancerRatio === null ? "—" : ratioPercent(playback.signal.advancerRatio)}</dd></div>
        <div>
          <dt>Signal weights</dt>
          <dd>
            {playback.strategy.momentumWeight === null || playback.strategy.volumeWeight === null
              ? "—"
              : `${fixed(playback.strategy.momentumWeight)} / ${fixed(playback.strategy.volumeWeight)}`}
            {playback.strategy.weightDate && <small> effective {displayDate(playback.strategy.weightDate)}</small>}
          </dd>
        </div>
        <div><dt>Source</dt><dd>{playback.signal.source ?? "Unavailable"}</dd></div>
      </dl>
      {notices.length > 0 && (
        <div className="playback-notices" role="status">{notices.map((notice) => <p key={notice}>{notice}</p>)}</div>
      )}
      <div className="playback-section-heading">
        <h3>Preserved operational basket</h3>
        <span className={`evidence-status evidence-status-${playback.basket.attributionStatus}`}>{playback.basket.attributionStatus} attribution</span>
      </div>
      {playback.basket.picks.length === 0 ? (
        <p className="evidence-empty-inline">No reviewed basket rows were stored.</p>
      ) : (
        <div className="table-scroll">
          <table className="evidence-table playback-table">
            <thead><tr><th>Pick</th><th>Candidate</th><th>Bucket</th><th>Score</th><th>Outcome</th></tr></thead>
            <tbody>
              {playback.basket.picks.map((pick) => (
                <tr key={pick.ticker}>
                  <td><strong>{pick.ticker}</strong>{pick.signals && <small>mom {fixed(pick.signals.momentum)} · vol {fixed(pick.signals.volume)} · penalty {fixed(pick.signals.setupPenalty)}</small>}</td>
                  <td>{pick.candidateRank === null ? "—" : `#${pick.candidateRank}`}</td>
                  <td>{pick.selectionBucket ? label(pick.selectionBucket) : "—"}</td>
                  <td>{fixed(pick.score)}</td>
                  <td className={valueTone(pick.outcome.returnPct)}>{percent(pick.outcome.returnPct)} <small>{pick.outcome.won ? "win" : "loss"}</small></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="playback-section-heading pilot-heading">
        <h3>Stored pilot comparison</h3>
        <span className={`evidence-status evidence-status-${playback.pilotComparison.status}`}>{playback.pilotComparison.status}</span>
      </div>
      {playback.pilotComparison.arms.length > 0 ? (
        <div className="playback-arm-grid">
          {playback.pilotComparison.arms.map((arm) => (
            <div key={arm.strategy}><span>{label(arm.strategy)}</span><strong className={valueTone(arm.averageReturn)}>{percent(arm.averageReturn)}</strong><small>{arm.wins}/{arm.evaluatedCount} wins · {arm.isComplete ? "complete" : "incomplete"}</small></div>
          ))}
        </div>
      ) : <p className="evidence-empty-inline">This signal snapshot has no stored paired pilot session.</p>}
    </section>
  );
}

type MissedMoverFilter = "all" | MissedMoverClassification;

function missedReason(reason: string) {
  const labels: Record<string, string> = {
    not_selected_by_score: "Passed the stored liquidity and volatility gates but was not selected by score.",
    low_liquidity: "Did not pass the stored traded-value liquidity gate.",
    extreme_volatility: "Moved beyond the stored momentum safety range.",
  };
  return labels[reason] ?? reason.replaceAll("_", " ");
}

function selectionNote(note: string) {
  const labels: Record<string, string> = {
    inside_top_pick_cutoff: "Ranked inside the normal pick cutoff.",
    below_top_pick_cutoff: "Ranked below the active pick cutoff.",
    excluded_by_breadth_cap: "Excluded because weak breadth reduced the basket size.",
    penalized_by_setup_context: "Setup context reduced the candidate's final score.",
  };
  return labels[note] ?? note.replaceAll("_", " ");
}

function MissedMoverDetail({ mover }: { mover: MissedMover }) {
  const signals = mover.attribution.signals;
  const adjustments = mover.attribution.adjustments;
  return (
    <div className="missed-mover-detail">
      <div className="missed-detail-heading">
        <div>
          <p className="eyebrow">Stored review evidence</p>
          <h3>{mover.ticker}</h3>
        </div>
        <strong className={valueTone(mover.returnPct)}>{percent(mover.returnPct)}</strong>
      </div>
      <div className="tag-row">
        <span className={`tag missed-${mover.classification}`}>{mover.classification.replace("_", " ")}</span>
        {mover.attribution.candidateRank !== null && <span className="tag tag-blue">rank #{mover.attribution.candidateRank}</span>}
      </div>
      <dl className="missed-summary">
        <div><dt>Classification reason</dt><dd>{missedReason(mover.reason)}</dd></div>
        <div><dt>Selection evidence</dt><dd>{selectionNote(mover.attribution.selectionNote)}</dd></div>
        <div><dt>Candidate status</dt><dd>{mover.attribution.dataStatus.replaceAll("_", " ")}</dd></div>
      </dl>
      {signals && adjustments ? (
        <>
          <h4>Point-in-time signals</h4>
          <dl className="missed-signal-grid">
            <div><dt>Momentum</dt><dd>{fixed(signals.momentum)}</dd></div>
            <div><dt>Volume</dt><dd>{fixed(signals.volume)}</dd></div>
            <div><dt>Technical</dt><dd>{signedFixed(signals.technical)}</dd></div>
            <div><dt>Fundamental</dt><dd>{signedFixed(signals.fundamental)}</dd></div>
            <div><dt>Quality</dt><dd>{signedFixed(signals.quality)}</dd></div>
            <div><dt>Setup penalty</dt><dd>{fixed(signals.setupPenalty)}</dd></div>
            <div><dt>Total boost</dt><dd>{signedFixed(adjustments.totalBoost)}</dd></div>
            <div><dt>Net adjustment</dt><dd>{signedFixed(adjustments.netAdjustment)}</dd></div>
          </dl>
        </>
      ) : (
        <p className="missed-no-signals">This mover was not present in the stored ranked-candidate evidence.</p>
      )}
    </div>
  );
}

function MissedMoverExplorer({ review }: { review: ReviewSummary }) {
  const [filter, setFilter] = useState<MissedMoverFilter>("all");
  const [selectedTicker, setSelectedTicker] = useState(review.missedMovers[0]?.ticker ?? "");

  if (review.missedMoversStatus === "not_captured") {
    return (
      <section className="panel missed-mover-panel" aria-labelledby="missed-mover-title">
        <h2 id="missed-mover-title">Missed-mover explorer</h2>
        <p className="missed-empty">This review predates persisted missed-mover evidence. It is left unchanged rather than recomputed with newer rules.</p>
      </section>
    );
  }

  if (review.missedMovers.length === 0) {
    return (
      <section className="panel missed-mover-panel" aria-labelledby="missed-mover-title">
        <h2 id="missed-mover-title">Missed-mover explorer</h2>
        <p className="missed-empty">No missed leading movers were captured for this review.</p>
      </section>
    );
  }

  const filtered = review.missedMovers.filter((mover) => filter === "all" || mover.classification === filter);
  const selectedMover = filtered.find((mover) => mover.ticker === selectedTicker) ?? filtered[0];
  const counts = {
    all: review.missedMovers.length,
    actionable: review.missedMovers.filter((mover) => mover.classification === "actionable").length,
    non_actionable: review.missedMovers.filter((mover) => mover.classification === "non_actionable").length,
  };

  return (
    <section className="panel missed-mover-panel" aria-labelledby="missed-mover-title">
      <div className="missed-panel-heading">
        <div>
          <p className="eyebrow">Review-time attribution</p>
          <h2 id="missed-mover-title">Missed-mover explorer</h2>
        </div>
        <p>Actionable means the mover passed stored liquidity and volatility gates—not that it is a recommendation.</p>
      </div>
      <div className="missed-filters" aria-label="Filter missed movers">
        {(["all", "actionable", "non_actionable"] as MissedMoverFilter[]).map((value) => (
          <button
            type="button"
            key={value}
            className={filter === value ? "is-active" : ""}
            aria-pressed={filter === value}
            onClick={() => setFilter(value)}
          >
            {value.replace("_", " ")} <span>{counts[value]}</span>
          </button>
        ))}
      </div>
      {filtered.length === 0 ? (
        <p className="missed-empty">No movers match this filter.</p>
      ) : (
        <div className="missed-explorer-layout">
          <div className="missed-mover-list" role="listbox" aria-label="Missed movers">
            {filtered.map((mover) => (
              <button
                type="button"
                role="option"
                aria-selected={selectedMover?.ticker === mover.ticker}
                className={selectedMover?.ticker === mover.ticker ? "is-selected" : ""}
                key={mover.ticker}
                onClick={() => setSelectedTicker(mover.ticker)}
              >
                <strong>{mover.ticker}</strong>
                <span className={valueTone(mover.returnPct)}>{percent(mover.returnPct)}</span>
                <small>{mover.classification.replace("_", " ")}</small>
              </button>
            ))}
          </div>
          {selectedMover && <MissedMoverDetail mover={selectedMover} />}
        </div>
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
  selectedPlayback,
  selectedReviewId,
  loading,
  error,
  onSelect,
}: {
  reviews: ReviewHistoryItem[];
  selectedReview: ReviewSummary | null;
  selectedPlayback: StrategyPlayback | null;
  selectedReviewId: number | null;
  loading: boolean;
  error: string | null;
  onSelect: (reviewId: number) => void;
}) {
  return (
    <div className="reviews-view">
      <div className="view-intro"><p className="eyebrow">Persisted performance</p><h2>Review past picks</h2><p>Replay each preserved signal basket, its exact market snapshot, and eventual recorded outcome.</p></div>
      <ReviewNavigator reviews={reviews} selectedId={selectedReviewId} loading={loading} onSelect={onSelect} />
      <div className="review-history-layout">
        <ReviewHistoryList reviews={reviews} selectedId={selectedReviewId} onSelect={onSelect} />
        <div className="review-detail" id="review-detail" aria-live="polite" aria-busy={loading}>
          {error && <p className="review-error" role="alert">{error}</p>}
          <StrategyPlaybackPanel playback={selectedPlayback} loading={loading} />
          <ReviewPanel
            review={selectedReview}
            title={selectedReview ? `Picks from ${displayDate(selectedReview.signalDate)}` : "Review details"}
            expanded
            loading={loading}
          />
          {!loading && !error && selectedReview && (
            <MissedMoverExplorer key={selectedReview.id} review={selectedReview} />
          )}
        </div>
      </div>
    </div>
  );
}

function EvidenceWindowControl({ value, onChange }: {
  value: EvidenceWindow;
  onChange: (value: EvidenceWindow) => void;
}) {
  return (
    <fieldset className="evidence-window-control">
      <legend>Review window</legend>
      <div>
        {evidenceWindowOptions.map((option) => (
          <button
            type="button"
            key={option}
            className={value === option ? "is-selected" : ""}
            aria-pressed={value === option}
            onClick={() => onChange(option)}
          >
            {option === "all" ? "All" : `Last ${option}`}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

function PilotPanel({ evidence }: { evidence: StrategyEvidence }) {
  const pilot = evidence.pilot;
  return (
    <section className="panel lab-pilot-panel" aria-labelledby="pilot-status-title">
      <div className="lab-panel-heading">
        <h3 id="pilot-status-title">Pilot status</h3>
        <span className={`evidence-status evidence-status-${pilot.status}`}>{label(pilot.status)}</span>
      </div>
      <dl className="lab-kpi-grid">
        <div><dt>Complete sessions</dt><dd>{pilot.completedSessions}/{pilot.thresholds.sessionTarget}</dd></div>
        <div><dt>Bucketed wins</dt><dd>{pilot.bucketedSessionWins}/{pilot.thresholds.minimumBucketedSessionWins}</dd></div>
        <div><dt>Compounded edge</dt><dd className={valueTone(pilot.compoundedEdge)}>{percent(pilot.compoundedEdge)}</dd></div>
        <div><dt>Active strategy</dt><dd>{label(pilot.selectedStrategy)}</dd></div>
      </dl>
      <dl className="compact-list lab-thresholds">
        <div><dt>Promotion edge</dt><dd>{percent(pilot.thresholds.promotionEdge)}</dd></div>
        <div><dt>Rollback edge</dt><dd>{percent(pilot.thresholds.rollbackEdge)}</dd></div>
        <div><dt>Decision</dt><dd>{label(pilot.decisionReason)}</dd></div>
      </dl>
    </section>
  );
}

function StrategyComparisonPanel({ evidence }: { evidence: StrategyEvidence }) {
  const score = findStrategySummary(evidence, "score_ranked");
  const bucketed = findStrategySummary(evidence, "bucketed");
  return (
    <section className="panel lab-comparison-panel" aria-labelledby="strategy-comparison-title">
      <div className="lab-panel-heading">
        <h3 id="strategy-comparison-title">Paired strategy comparison</h3>
        <span className={`evidence-status evidence-status-${evidence.comparison.status}`}>{evidence.comparison.status}</span>
      </div>
      <div className="strategy-compare-grid">
        {[score, bucketed].map((strategy) => strategy && (
          <article key={strategy.strategy}>
            <h4>{label(strategy.strategy)}</h4>
            <strong className={valueTone(strategy.compoundedReturn)}>{percent(strategy.compoundedReturn)}</strong>
            <span>Compounded return</span>
            <dl>
              <div><dt>Average session</dt><dd>{percent(strategy.averageSessionReturn)}</dd></div>
              <div><dt>Pick win rate</dt><dd>{ratioPercent(strategy.pickWinRate)}</dd></div>
              <div><dt>Evaluated picks</dt><dd>{strategy.evaluatedCount}</dd></div>
            </dl>
          </article>
        ))}
      </div>
      <p className="evidence-coverage">
        {evidence.comparison.completePairedSessions} complete paired sessions · {evidence.comparison.bucketedSessionWins} bucketed session wins
        {evidence.comparison.incompletePairedSessions > 0 && ` · ${evidence.comparison.incompletePairedSessions} incomplete`}
        {evidence.comparison.unpairedSessions > 0 && ` · ${evidence.comparison.unpairedSessions} unpaired`}
      </p>
    </section>
  );
}

function CandidateEvidencePanel({ evidence }: { evidence: StrategyEvidence }) {
  const candidates = evidence.candidateEvidence;
  return (
    <section className="panel candidate-evidence-panel" aria-labelledby="candidate-evidence-title">
      <div className="lab-panel-heading">
        <h3 id="candidate-evidence-title">Candidate evidence</h3>
        <span className={`evidence-status evidence-status-${candidates.status}`}>{candidates.status}</span>
      </div>
      <p className="evidence-coverage">{candidates.candidateCount} candidates across {candidates.sessionCount} captured sessions</p>
      <div className="candidate-evidence-grid">
        <div>
          <h4>Cutoff analysis</h4>
          <div className="table-scroll">
            <table className="evidence-table">
              <thead><tr><th>Cutoff</th><th>Count</th><th>Avg return</th><th>Win rate</th></tr></thead>
              <tbody>
                {candidates.cutoffAnalysis.cutoffs.map((row) => (
                  <tr key={row.cutoff} className={candidates.cutoffAnalysis.bestCutoff === row.cutoff ? "is-best" : ""}>
                    <td>{label(row.cutoff)}{candidates.cutoffAnalysis.bestCutoff === row.cutoff && <span className="best-mark">Best</span>}</td>
                    <td>{row.count}</td><td className={valueTone(row.averageReturn)}>{percent(row.averageReturn)}</td><td>{ratioPercent(row.winRate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div>
          <h4>Rank bands</h4>
          <div className="rank-band-list">
            {candidates.rankBands.map((row) => (
              <div key={row.band}>
                <strong>{row.band}</strong>
                <span>{row.count} candidates</span>
                <b className={valueTone(row.averageReturn)}>{percent(row.averageReturn)}</b>
                <span>{ratioPercent(row.winRate)} wins</span>
              </div>
            ))}
          </div>
          <h4>Setup penalty</h4>
          <div className="setup-compare-list">
            {([
              ["Penalized", candidates.setupPenalty.penalized],
              ["No penalty", candidates.setupPenalty.unpenalized],
            ] as const).map(([name, row]) => (
              <div key={name}>
                <strong>{name}</strong><span>{row.count} candidates</span>
                <b className={valueTone(row.averageReturn)}>{percent(row.averageReturn)}</b>
                <span>{ratioPercent(row.winRate)} wins</span>
              </div>
            ))}
          </div>
          <p className="evidence-coverage">Average stored penalty {fixed(candidates.setupPenalty.averagePenalty)}</p>
        </div>
      </div>
    </section>
  );
}

function BreadthEvidencePanel({ evidence }: { evidence: StrategyEvidence }) {
  const breadth = evidence.breadth;
  return (
    <section className="panel breadth-evidence-panel" aria-labelledby="breadth-evidence-title">
      <div className="lab-panel-heading">
        <h3 id="breadth-evidence-title">Signal-snapshot breadth</h3>
        <span className={`evidence-status evidence-status-${breadth.status}`}>{breadth.status}</span>
      </div>
      <dl className="lab-kpi-grid breadth-kpis">
        <div><dt>Average advancers</dt><dd>{breadth.averageAdvancerRatio === null ? "—" : ratioPercent(breadth.averageAdvancerRatio)}</dd></div>
        <div><dt>Minimum</dt><dd>{breadth.minimumAdvancerRatio === null ? "—" : ratioPercent(breadth.minimumAdvancerRatio)}</dd></div>
        <div><dt>Maximum</dt><dd>{breadth.maximumAdvancerRatio === null ? "—" : ratioPercent(breadth.maximumAdvancerRatio)}</dd></div>
        <div><dt>Exact snapshots</dt><dd>{breadth.availableSessionCount}/{evidence.window.includedReviewCount}</dd></div>
      </dl>
      <div className="breadth-session-list">
        {breadth.sessions.map((session) => (
          <div key={session.reviewId}>
            <span>{displayDate(session.signalDate)}</span>
            <div className="breadth-bar" aria-label={session.advancerRatio === null ? "Breadth unavailable" : `${ratioPercent(session.advancerRatio)} advancers`}>
              <i style={{ width: `${(session.advancerRatio ?? 0) * 100}%` }} />
            </div>
            <strong>{session.advancerRatio === null ? "Unavailable" : ratioPercent(session.advancerRatio)}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}

function PilotSessionTable({ evidence }: { evidence: StrategyEvidence }) {
  return (
    <section className="panel pilot-session-panel" aria-labelledby="pilot-session-title">
      <h3 id="pilot-session-title">Persisted pilot sessions</h3>
      {evidence.comparison.sessions.length === 0 ? (
        <p className="evidence-empty-inline">No persisted pilot sessions fall inside this review window.</p>
      ) : (
        <div className="table-scroll">
          <table className="evidence-table session-table">
            <thead><tr><th>Signal date</th><th>Pair</th><th>Score-ranked</th><th>Bucketed</th></tr></thead>
            <tbody>
              {evidence.comparison.sessions.map((session) => (
                <tr key={session.signalSnapshotId}>
                  <td>{displayDate(session.signalDate)}</td>
                  <td><span className={`evidence-status evidence-status-${session.pairStatus}`}>{session.pairStatus}</span></td>
                  <td className={session.scoreRanked ? valueTone(session.scoreRanked.averageReturn) : "neutral"}>{session.scoreRanked ? percent(session.scoreRanked.averageReturn) : "—"}</td>
                  <td className={session.bucketed ? valueTone(session.bucketed.averageReturn) : "neutral"}>{session.bucketed ? percent(session.bucketed.averageReturn) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function DiagnosticsView({
  picks,
  selectedPick,
  onSelect,
  evidence,
  evidenceStatus,
  evidenceError,
  evidenceWindow,
  onEvidenceWindowChange,
  onRetryEvidence,
}: {
  picks: Pick[];
  selectedPick: Pick | null;
  onSelect: (ticker: string) => void;
  evidence: StrategyEvidence | null;
  evidenceStatus: "idle" | "loading" | "loaded" | "error";
  evidenceError: string | null;
  evidenceWindow: EvidenceWindow;
  onEvidenceWindowChange: (window: EvidenceWindow) => void;
  onRetryEvidence: () => void;
}) {
  const displayState = evidenceDisplayState(evidence);
  return (
    <div className="diagnostics-view">
      <header className="strategy-lab-header">
        <div><h2>Strategy evidence lab</h2><p>Persisted reviews, candidate outcomes, pilot sessions, and exact signal snapshots.</p></div>
        <EvidenceWindowControl value={evidenceWindow} onChange={onEvidenceWindowChange} />
      </header>
      {evidenceStatus === "loading" && !evidence && (
        <section className="panel evidence-loading" aria-live="polite"><SpinnerGap className="spin" size={24} /> Loading strategy evidence…</section>
      )}
      {evidenceStatus === "error" && (
        <section className="panel evidence-error" role="alert"><p>{evidenceError}</p><button type="button" className="secondary-action" onClick={onRetryEvidence}>Retry</button></section>
      )}
      {evidence && evidence.status === "empty" && evidenceStatus !== "error" && (
        <section className="panel evidence-empty"><h3>No persisted review evidence</h3><p>Run and review a persisted basket before using the Strategy Evidence Lab.</p></section>
      )}
      {evidence && evidence.status === "available" && evidenceStatus !== "error" && (
        <>
          <div className="evidence-window-meta" aria-live="polite">
            <span>{evidence.window.includedReviewCount} of {evidence.window.availableReviewCount} reviews</span>
            <span>{displayDate(evidence.window.startReviewDate ?? "—")} → {displayDate(evidence.window.endReviewDate ?? "—")}</span>
            {evidenceStatus === "loading" && <span><SpinnerGap className="spin" size={16} /> Updating</span>}
          </div>
          {displayState.notices.length > 0 && (
            <div className="evidence-notices" role="status">{displayState.notices.map((notice) => <p key={notice}>{notice}</p>)}</div>
          )}
          <div className="lab-summary-grid"><PilotPanel evidence={evidence} /><StrategyComparisonPanel evidence={evidence} /></div>
          <CandidateEvidencePanel evidence={evidence} />
          <div className="lab-detail-grid"><BreadthEvidencePanel evidence={evidence} /><PilotSessionTable evidence={evidence} /></div>
        </>
      )}
      <div className="latest-pick-heading"><h3>Latest persisted pick evidence</h3><p>Normalized signals and bounded adjustments for the selected latest pick.</p></div>
      {selectedPick ? (
        <div className="latest-pick-grid"><PickList picks={picks} selectedTicker={selectedPick.ticker} onSelect={onSelect} /><EvidencePanel pick={selectedPick} /></div>
      ) : (
        <section className="panel evidence-empty"><h3>No latest persisted picks</h3><p>Strategy evidence remains available above; run the persisted routine to populate latest-pick diagnostics.</p></section>
      )}
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
  const strategyEvidence = useStrategyEvidence(
    strategyEvidenceRepository,
    activeView === "diagnostics",
  );
  const [selectedTicker, setSelectedTicker] = useState("AKSEN");
  const [selectedReviewId, setSelectedReviewId] = useState<number | null>(null);
  const [selectedReview, setSelectedReview] = useState<ReviewSummary | null>(null);
  const [selectedPlayback, setSelectedPlayback] = useState<StrategyPlayback | null>(null);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const reviewRequestId = useRef(0);

  useEffect(() => {
    const requestId = ++reviewRequestId.current;
    setReviewLoading(false);
    setSelectedReviewId(data?.review?.id ?? null);
    setSelectedReview(data?.review ?? null);
    setSelectedPlayback(null);
    setReviewError(null);
    if (activeView === "reviews" && data?.review) {
      setReviewLoading(true);
      void dashboardRepository.loadPlayback(data.review.id)
        .then((playback) => {
          if (requestId !== reviewRequestId.current) return;
          setSelectedPlayback(playback);
          setSelectedReview(playback.review);
        })
        .catch((error) => {
          if (requestId !== reviewRequestId.current) return;
          setReviewError(error instanceof Error ? error.message : "The selected playback could not be loaded.");
        })
        .finally(() => {
          if (requestId === reviewRequestId.current) setReviewLoading(false);
        });
    }
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
    if (selectedPlayback?.review.id === reviewId) {
      revealReviewDetail();
      return;
    }
    const requestId = ++reviewRequestId.current;
    setSelectedReviewId(reviewId);
    setReviewError(null);
    setReviewLoading(true);
    revealReviewDetail();
    try {
      const playback = await dashboardRepository.loadPlayback(reviewId);
      if (requestId === reviewRequestId.current) {
        setSelectedPlayback(playback);
        setSelectedReview(playback.review);
      }
    } catch (error) {
      if (requestId === reviewRequestId.current) {
        setSelectedPlayback(null);
        setSelectedReview(null);
        setReviewError(error instanceof Error ? error.message : "The selected playback could not be loaded.");
      }
    } finally {
      if (requestId === reviewRequestId.current) setReviewLoading(false);
    }
  };

  const navigate = (view: ViewKey) => {
    setActiveView(view);
    if (view === "reviews" && selectedReviewId !== null && selectedPlayback?.review.id !== selectedReviewId) {
      void selectReview(selectedReviewId);
    }
    const url = new URL(window.location.href);
    if (view === "picks") {
      url.searchParams.delete("view");
    } else {
      url.searchParams.set("view", view);
    }
    window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
  };

  const contentMode = appContentMode(activeView, data !== null);
  const renderView = () => {
    if (contentMode === "strategy_lab") {
      return (
        <DiagnosticsView
          picks={data?.picks ?? []}
          selectedPick={selectedPick ?? null}
          onSelect={selectPick}
          evidence={strategyEvidence.evidence}
          evidenceStatus={strategyEvidence.status}
          evidenceError={strategyEvidence.error}
          evidenceWindow={strategyEvidence.window}
          onEvidenceWindowChange={strategyEvidence.setWindow}
          onRetryEvidence={() => void strategyEvidence.reload()}
        />
      );
    }
    if (contentMode === "dashboard_unavailable" || !data) {
      return <StatusView kind={status === "error" ? "empty" : "loading"} onRetry={() => void reload()} />;
    }
    if (activeView === "overview") return <OverviewView data={data} onNavigate={navigate} />;
    if (activeView === "reviews") {
      return (
        <ReviewsView
          reviews={data.reviewHistory}
          selectedReview={selectedReview}
          selectedPlayback={selectedPlayback}
          selectedReviewId={selectedReviewId}
          loading={reviewLoading}
          error={reviewError}
          onSelect={(reviewId) => void selectReview(reviewId)}
        />
      );
    }
    if (activeView === "runs") return <RunsView data={data} reload={async () => {
      await Promise.all([reload(), strategyEvidence.reload()]);
    }} />;
    if (!selectedPick) return <StatusView kind="empty" onRetry={() => void reload()} />;

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
    <div className={`app-shell${contentMode === "dashboard_unavailable" ? " boot-shell" : ""}`}>
      <Sidebar activeView={activeView} onNavigate={navigate} />
      <main className="workspace">
        {data && <SessionHeader data={data} />}
        {renderView()}
      </main>
    </div>
  );
}
