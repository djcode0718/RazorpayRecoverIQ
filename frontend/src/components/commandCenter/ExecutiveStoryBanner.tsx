import { Summary, OpportunityListItem } from "../../types";
import { computeExecutiveWhyThisMatters } from "../../utils/calculations";

type ExecutiveStoryBannerProps = {
  summary: Summary;
  opportunities: OpportunityListItem[];
  onOpenDemoTour?: () => void;
};

export function ExecutiveStoryBanner({ summary, opportunities }: ExecutiveStoryBannerProps) {
  const whyItMatters = computeExecutiveWhyThisMatters(opportunities, summary.gross_recovered_minor);

  return (
    <section className="executive-story-compact-banner panel" aria-label="Recovery Lifecycle Loop">
      <div className="compact-loop-header">
        <span className="compact-loop-tag">AUTONOMOUS RECOVERY LOOP</span>
        <div className="compact-briefing-snippet">
          <span className="briefing-icon">💡</span>
          <strong className="briefing-label">Executive Briefing:</strong>
          <span className="briefing-text">{whyItMatters.headline}</span>
        </div>
      </div>

      <div className="compact-lifecycle-flow">
        <div className="compact-flow-step">
          <span className="step-badge">1</span>
          <div className="step-meta">
            <strong>Detect</strong>
            <span>Failed Webhooks</span>
          </div>
        </div>
        <span className="compact-flow-arrow">&rarr;</span>

        <div className="compact-flow-step">
          <span className="step-badge">2</span>
          <div className="step-meta">
            <strong>Diagnose</strong>
            <span>ML Conviction</span>
          </div>
        </div>
        <span className="compact-flow-arrow">&rarr;</span>

        <div className="compact-flow-step">
          <span className="step-badge">3</span>
          <div className="step-meta">
            <strong>Approve</strong>
            <span>7/7 Policy Gates</span>
          </div>
        </div>
        <span className="compact-flow-arrow">&rarr;</span>

        <div className="compact-flow-step">
          <span className="step-badge">4</span>
          <div className="step-meta">
            <strong>Recover</strong>
            <span>Razorpay Smart Link</span>
          </div>
        </div>
        <span className="compact-flow-arrow">&rarr;</span>

        <div className="compact-flow-step highlight">
          <span className="step-badge check">✓</span>
          <div className="step-meta">
            <strong>Verify</strong>
            <span>HMAC Captured</span>
          </div>
        </div>
      </div>
    </section>
  );
}
