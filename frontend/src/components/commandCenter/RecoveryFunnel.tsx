import { Fragment } from "react";
import { Summary } from "../../types";
import { formatMinorCurrency } from "../../utils/formatters";

type RecoveryFunnelProps = {
  funnel: Summary["funnel"];
};

export function RecoveryFunnel({ funnel }: RecoveryFunnelProps) {
  const atRisk = funnel.revenue_at_risk_minor > 0 ? funnel.revenue_at_risk_minor : 1;

  const stages = [
    {
      num: 1,
      name: "Revenue at Risk",
      val: funnel.revenue_at_risk_minor,
      tone: "neutral",
      fillClass: "fill-risk",
      color: "var(--text)",
    },
    {
      num: 2,
      name: "AI Diagnosed",
      val: funnel.ai_identifiable_minor,
      tone: "info",
      fillClass: "fill-info",
      color: "var(--info-text)",
    },
    {
      num: 3,
      name: "Policy Approved",
      val: funnel.policy_eligible_minor,
      tone: "accent",
      fillClass: "fill-accent",
      color: "var(--accent)",
    },
    {
      num: 4,
      name: "Recovery Attempted",
      val: funnel.recovery_attempted_minor,
      tone: "primary",
      fillClass: "fill-primary",
      color: "var(--primary)",
    },
    {
      num: 5,
      name: "Successfully Recovered",
      val: funnel.successfully_recovered_minor,
      tone: "good",
      fillClass: "fill-good",
      color: "var(--good-text)",
    },
  ];

  const overallConversion = Math.round((funnel.successfully_recovered_minor / atRisk) * 100);

  return (
    <div className="panel funnel-panel visual-funnel-card">
      <div className="panel-header-with-badge">
        <div>
          <h2>Recovery Conversion Funnel</h2>
          <p className="panel-copy">Multi-stage conversion from raw failure to settled recovery.</p>
        </div>
        <span className="badge badge-good badge-sm">
          {overallConversion}% End-to-End
        </span>
      </div>

      <div className="visual-funnel-stages">
        {stages.map((stage, idx) => {
          const prevVal = idx > 0 ? stages[idx - 1].val : stage.val;
          const stepConversion = prevVal > 0 ? Math.round((stage.val / prevVal) * 100) : 0;
          const pctOfTotal = Math.min(Math.round((stage.val / atRisk) * 100), 100);

          return (
            <Fragment key={stage.name}>
              <div className="funnel-visual-row">
                <div className="funnel-step-badge">{stage.num}</div>
                <div className="funnel-row-main">
                  <div className="funnel-row-head">
                    <span className="funnel-stage-title">{stage.name}</span>
                    <div className="funnel-amount-group">
                      <strong className="funnel-amount" style={{ color: stage.color }}>
                        {formatMinorCurrency(stage.val)}
                      </strong>
                      <span className="funnel-total-pct">({pctOfTotal}%)</span>
                    </div>
                  </div>
                  <div className="funnel-track-bg">
                    <div
                      className={`funnel-track-fill ${stage.fillClass}`}
                      style={{ width: `${Math.max(pctOfTotal, 4)}%` }}
                    />
                  </div>
                </div>
              </div>

              {idx < stages.length - 1 && (
                <div className="funnel-step-connector">
                  <span className="connector-line" />
                  <span className="connector-pill">
                    ↓ {stepConversion}% step conversion
                  </span>
                  <span className="connector-line" />
                </div>
              )}
            </Fragment>
          );
        })}
      </div>
    </div>
  );
}
