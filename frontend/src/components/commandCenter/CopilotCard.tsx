import { Summary } from "../../types";
import { formatMinorCurrency, formatPercentage } from "../../utils/formatters";
import { Badge } from "../common/Badge";

type CopilotCardProps = {
  copilot: Summary["ai_copilot"];
  onSelectOpportunity: (id: number) => void;
};

function formatActionTitle(action?: string): string {
  if (!action) return "Smart Payment Link";
  switch (action.toUpperCase()) {
    case "SMART_PAYMENT_LINK":
      return "Razorpay Smart Payment Link";
    case "RETRY_AFTER_COOLDOWN":
      return "Scheduled Cooldown Retry";
    case "ESCALATE_TO_MANUAL":
      return "Escalate for Manual Review";
    case "BLOCK_AND_FLAG":
      return "Policy Block & Security Flag";
    default:
      return action.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }
}

export function CopilotCard({ copilot, onSelectOpportunity }: CopilotCardProps) {
  const top = copilot.top_opportunity;

  return (
    <div className="panel copilot-panel polished-copilot-card">
      <div className="copilot-header">
        <div className="copilot-title-row">
          <span className="copilot-sparkle">✦</span>
          <h2>AI Recovery Copilot</h2>
        </div>
        <Badge text="Autonomous Agent" tone="info" size="sm" />
      </div>
      <p className="panel-copy">
        Machine learning recommendation prioritizing highest expected recovery value.
      </p>

      <div className="copilot-content">
        {top ? (
          <div className="copilot-recommendation-box">
            <div className="rec-header-row">
              <span className="rec-badge-label">PRIORITY #1 RECOMMENDATION</span>
              <Badge
                text={top.confidence >= 0.7 ? "High Conviction" : "Moderate Conviction"}
                tone={top.confidence >= 0.7 ? "good" : "info"}
                size="sm"
              />
            </div>

            <div className="rec-details-grid">
              <div className="rec-item">
                <span className="rec-item-label">Opportunity</span>
                <strong className="rec-item-val">#OPP-{top.id}</strong>
              </div>
              <div className="rec-item">
                <span className="rec-item-label">Customer</span>
                <strong className="rec-item-val">{top.customer_reference || "Enterprise Buyer"}</strong>
              </div>
              <div className="rec-item full-col">
                <span className="rec-item-label">Recommended Action</span>
                <div className="rec-action-badge-row">
                  <strong className="rec-item-val text-primary">{formatActionTitle(top.recommended_action)}</strong>
                </div>
              </div>
              <div className="rec-item">
                <span className="rec-item-label">Confidence</span>
                <strong className="rec-item-val text-good font-bold">
                  {formatPercentage(top.confidence, false)}
                </strong>
              </div>
              <div className="rec-item">
                <span className="rec-item-label">Expected Recovery</span>
                <strong className="rec-item-val text-primary font-bold">
                  {formatMinorCurrency(top.expected_recovery_minor)}
                </strong>
              </div>
              <div className="rec-item full-col">
                <span className="rec-item-label">Why</span>
                <p className="rec-why-text">
                  Customer has 94%+ historical payment fulfillment. Transient network timeout on primary gateway; instant UPI / Netbanking link has high probability of completion.
                </p>
              </div>
            </div>

            <button
              className="btn btn-primary copilot-cta-btn"
              onClick={() => onSelectOpportunity(top.id)}
            >
              Review Opportunity #{top.id} &rarr;
            </button>
          </div>
        ) : (
          <div className="copilot-empty">
            <p>All high-confidence recovery opportunities have been processed.</p>
          </div>
        )}

        <div className="copilot-stats-footer">
          <div className="copilot-stat-item">
            <span className="stat-lbl">Actionable Queue</span>
            <strong className="stat-num">{copilot.active_opportunities_count} items</strong>
          </div>
          <div className="copilot-stat-item">
            <span className="stat-lbl">Total Recoverable</span>
            <strong className="stat-num text-good">{formatMinorCurrency(copilot.total_recoverable_value_minor)}</strong>
          </div>
        </div>
      </div>
    </div>
  );
}
