import { Summary, OperatingStatus } from "../../types";
import { formatMinorCurrency } from "../../utils/formatters";
import { Badge } from "../common/Badge";

type ActionableInsightsProps = {
  summary: Summary;
  operatingStatus: OperatingStatus;
};

export function ActionableInsights({ summary, operatingStatus }: ActionableInsightsProps) {
  const isEscalated = summary.escalations > 0 || (summary.blocked_actions || 0) > 0;

  return (
    <section className="executive-insights-grid" aria-label="Executive Decision Insights">
      {/* 1. WHAT CHANGED */}
      <article className="insight-card-structured panel">
        <div className="insight-card-top">
          <div className="insight-title-group">
            <span className="insight-tag">1. RECENT ACTIVITY</span>
            <h3>What Changed</h3>
          </div>
          <Badge text={`${summary.recovery_attempts} Attempted`} tone="info" size="sm" />
        </div>

        <div className="insight-structured-body">
          <div className="insight-row">
            <span className="row-q">What happened:</span>
            <p className="row-a">
              {operatingStatus.last_event
                ? `Latest event: ${operatingStatus.last_event}. Gross recovered: ${formatMinorCurrency(summary.gross_recovered_minor)}.`
                : `${summary.active_opportunities} open payment failures ingested and classified by ML.`}
            </p>
          </div>
          <div className="insight-row">
            <span className="row-q">Why it matters:</span>
            <p className="row-a">
              Real-time recovery intercepts drop-offs within minutes before cart abandonment becomes permanent.
            </p>
          </div>
          <div className="insight-row action-row">
            <span className="row-q">What to do:</span>
            <p className="row-a text-good font-bold">
              Review prioritized recovery queue below to dispatch high-conviction actions.
            </p>
          </div>
        </div>
      </article>

      {/* 2. WHERE MONEY IS AT RISK */}
      <article className="insight-card-structured panel">
        <div className="insight-card-top">
          <div className="insight-title-group">
            <span className="insight-tag">2. CAPITAL EXPOSURE</span>
            <h3>Where Money Is At Risk</h3>
          </div>
          <Badge text={`${formatMinorCurrency(summary.revenue_at_risk_minor)} Exposure`} tone="warn" size="sm" />
        </div>

        <div className="insight-structured-body">
          <div className="insight-row">
            <span className="row-q">What happened:</span>
            <p className="row-a">
              Primary losses concentrate in bank gateway timeouts and card issuer declines.
            </p>
          </div>
          <div className="insight-row">
            <span className="row-q">Why it matters:</span>
            <p className="row-a">
              Blind retries cause issuer penalties; AI routing converts genuine customer intent to alternate payment rails.
            </p>
          </div>
          <div className="insight-row action-row">
            <span className="row-q">What to do:</span>
            <p className="row-a text-primary font-bold">
              Deploy Razorpay Smart Payment Links with pre-warmed UPI & alternate card checkout.
            </p>
          </div>
        </div>
      </article>

      {/* 3. MANAGER ATTENTION */}
      <article className="insight-card-structured panel">
        <div className="insight-card-top">
          <div className="insight-title-group">
            <span className="insight-tag">3. POLICY & GOVERNANCE</span>
            <h3>Manager Attention</h3>
          </div>
          <Badge
            text={isEscalated ? `${summary.escalations} Escalated` : "All Clear"}
            tone={isEscalated ? "warn" : "good"}
            size="sm"
          />
        </div>

        <div className="insight-structured-body">
          <div className="insight-row">
            <span className="row-q">What happened:</span>
            <p className="row-a">
              {isEscalated
                ? `${summary.escalations} transactions escalated & ${summary.blocked_actions || 0} held by safety gates.`
                : "100% of open opportunities satisfy automated safety threshold bounds."}
            </p>
          </div>
          <div className="insight-row">
            <span className="row-q">Why it matters:</span>
            <p className="row-a">
              Deterministic policy rules block duplicate charges and respect velocity limits automatically.
            </p>
          </div>
          <div className="insight-row action-row">
            <span className="row-q">What to do:</span>
            <p className="row-a text-info font-bold">
              {isEscalated ? "Inspect manual approval queue before releasing hold." : "Autonomous loop operating normally."}
            </p>
          </div>
        </div>
      </article>
    </section>
  );
}
