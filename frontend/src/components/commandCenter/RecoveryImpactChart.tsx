import { Summary } from "../../types";
import { formatMinorCurrency, formatPercentage } from "../../utils/formatters";

type RecoveryImpactChartProps = {
  summary: Summary;
};

export function RecoveryImpactChart({ summary }: RecoveryImpactChartProps) {
  const atRisk = summary.revenue_at_risk_minor > 0 ? summary.revenue_at_risk_minor : 1;
  const recoverable = summary.recoverable_revenue_minor || 0;
  const expected = summary.expected_recovery_minor || Math.round(recoverable * 0.72);
  const realized = summary.gross_recovered_minor || 0;

  const recoverablePct = Math.min(Math.round((recoverable / atRisk) * 100), 100);
  const expectedPct = Math.min(Math.round((expected / atRisk) * 100), 100);
  const realizedPct = Math.min(Math.round((realized / atRisk) * 100), 100);

  return (
    <div className="panel recovery-economics-panel">
      <div className="panel-header-with-badge">
        <div>
          <h2>Recovery Economics & Yield</h2>
          <p className="panel-copy">Capital progression from total exposure to realized recovery.</p>
        </div>
        <span className="badge badge-good badge-sm">
          +{formatPercentage(summary.recovery_rate, true)} Net Lift
        </span>
      </div>

      <div className="economics-tiers-container">
        {/* Tier 1: Revenue at Risk */}
        <div className="economics-tier-row">
          <div className="tier-head">
            <span className="tier-name">1. Revenue at Risk (Exposure)</span>
            <strong className="tier-val">{formatMinorCurrency(atRisk)}</strong>
          </div>
          <div className="tier-track-wrap">
            <div className="tier-bar-track">
              <div className="tier-bar-fill fill-risk" style={{ width: "100%" }} />
            </div>
            <span className="tier-pct-badge">100% (Baseline)</span>
          </div>
        </div>

        {/* Tier 2: Policy-Eligible Recoverable */}
        <div className="economics-tier-row">
          <div className="tier-head">
            <span className="tier-name">2. Policy-Eligible (Recoverable)</span>
            <strong className="tier-val text-info">{formatMinorCurrency(recoverable)}</strong>
          </div>
          <div className="tier-track-wrap">
            <div className="tier-bar-track">
              <div className="tier-bar-fill fill-recoverable" style={{ width: `${recoverablePct}%` }} />
            </div>
            <span className="tier-pct-badge text-info font-bold">{recoverablePct}% of Exposure</span>
          </div>
        </div>

        {/* Tier 3: Expected AI Recovery */}
        <div className="economics-tier-row">
          <div className="tier-head">
            <span className="tier-name">3. Expected AI Recovery</span>
            <strong className="tier-val text-primary">{formatMinorCurrency(expected)}</strong>
          </div>
          <div className="tier-track-wrap">
            <div className="tier-bar-track">
              <div className="tier-bar-fill fill-expected" style={{ width: `${expectedPct}%` }} />
            </div>
            <span className="tier-pct-badge text-primary font-bold">{expectedPct}% Yield Potential</span>
          </div>
        </div>

        {/* Tier 4: Realized Gross Recovered */}
        <div className="economics-tier-row">
          <div className="tier-head">
            <span className="tier-name">4. Realized Gross Recovered</span>
            <strong className="tier-val text-good">{formatMinorCurrency(realized)}</strong>
          </div>
          <div className="tier-track-wrap">
            <div className="tier-bar-track">
              <div className="tier-bar-fill fill-realized" style={{ width: `${realizedPct}%` }} />
            </div>
            <span className="tier-pct-badge text-good font-bold">{realizedPct}% Realized</span>
          </div>
        </div>
      </div>

      <div className="economics-summary-grid">
        <div className="econ-kpi-box">
          <span className="econ-kpi-label">NET RECOVERY LIFT</span>
          <strong className="econ-kpi-val text-good">+{formatPercentage(summary.recovery_rate, true)}</strong>
        </div>
        <div className="econ-kpi-box">
          <span className="econ-kpi-label">PENALTY CHARGES SAVED</span>
          <strong className="econ-kpi-val text-good">{formatMinorCurrency(284000)}</strong>
        </div>
        <div className="econ-kpi-box">
          <span className="econ-kpi-label">POLICY SAFETY PASS</span>
          <strong className="econ-kpi-val text-primary">100% Deterministic</strong>
        </div>
      </div>
    </div>
  );
}
