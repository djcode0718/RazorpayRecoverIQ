import { Summary } from "../../types";
import { formatMinorCurrency, formatPercentage } from "../../utils/formatters";
import { KpiCard } from "../common/KpiCard";

type ExecutiveKpiGridProps = {
  summary: Summary;
  onNavigateTab: (tab: string, filter?: Record<string, string>) => void;
};

export function ExecutiveKpiGrid({ summary, onNavigateTab }: ExecutiveKpiGridProps) {
  const totalBlockedEscalated = (summary.blocked_actions || 0) + (summary.escalations || 0);

  return (
    <section className="kpi-hierarchy-grid" aria-label="Executive KPI Metrics">
      <KpiCard
        title="Recoverable Revenue"
        value={formatMinorCurrency(summary.recoverable_revenue_minor)}
        highlightTone="info"
        subtext="Policy-eligible capital pipeline"
        onClick={() => onNavigateTab("Opportunities", { status: "OPEN" })}
        tooltip="Click to inspect open policy-eligible opportunities"
      />

      <KpiCard
        title="Expected Recovery"
        value={formatMinorCurrency(summary.expected_recovery_minor || Math.round(summary.recoverable_revenue_minor * 0.72))}
        highlightTone="info"
        subtext="AI conviction-weighted forecast"
        onClick={() => onNavigateTab("Opportunities", { status: "OPEN" })}
        tooltip="Click to view expected value opportunities"
      />

      <KpiCard
        title="Recovered Revenue"
        value={formatMinorCurrency(summary.gross_recovered_minor)}
        highlightTone="good"
        isHero
        badge={{ text: "Realized", tone: "good" }}
        subtext={`+${formatPercentage(summary.recovery_rate, true)} net capital yield captured`}
        onClick={() => onNavigateTab("Opportunities", { status: "RESOLVED" })}
        tooltip="Click to view settled Razorpay recoveries"
      />

      <KpiCard
        title="Recovery Rate"
        value={formatPercentage(summary.recovery_rate, true)}
        highlightTone={summary.recovery_rate > 0 ? "good" : undefined}
        subtext="Realized / Recoverable yield"
        onClick={() => onNavigateTab("Evaluation")}
        tooltip="Click to view model benchmark & comparison matrix"
      />

      <KpiCard
        title="Active Opportunities"
        value={String(summary.active_opportunities)}
        subtext={`${summary.recovery_attempts} automated recovery loops`}
        onClick={() => onNavigateTab("Opportunities")}
        tooltip="Click to inspect all active recovery opportunities"
      />

      <KpiCard
        title="Attention Needed"
        value={String(totalBlockedEscalated)}
        highlightTone={totalBlockedEscalated > 0 ? "warn" : undefined}
        subtext={`${summary.blocked_actions || 0} blocked by policy &bull; ${summary.escalations || 0} escalated`}
        onClick={() => onNavigateTab("Opportunities", { status: "ALL" })}
        tooltip="Click to inspect policy blocks and escalated transactions"
      />
    </section>
  );
}
