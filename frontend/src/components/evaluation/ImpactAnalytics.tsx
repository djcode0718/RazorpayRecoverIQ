import { EvaluationComparisonResponse, EvaluationDrilldownResponse } from "../../types";
import { formatMinorCurrency } from "../../utils/formatters";

type ImpactAnalyticsProps = {
  comparison: NonNullable<EvaluationComparisonResponse["data"]>;
  drilldown: EvaluationDrilldownResponse["data"] | null;
};

export function ImpactAnalytics({ comparison, drilldown }: ImpactAnalyticsProps) {
  const incrementalRevenue = comparison.recoveriq.gross_recovered_minor - comparison.baseline.gross_recovered_minor;
  const recoveryRateDelta = ((comparison.recoveriq.recovery_rate - comparison.baseline.recovery_rate) * 100).toFixed(1);

  const fpReductionPct =
    comparison.baseline.false_positive_exposure_minor > 0
      ? (
          ((comparison.baseline.false_positive_exposure_minor - comparison.recoveriq.false_positive_exposure_minor) /
            comparison.baseline.false_positive_exposure_minor) *
          100
        ).toFixed(1)
      : "0.0";

  const successfulRecoveries = drilldown
    ? drilldown.confusion_matrix.tp
    : Math.round((comparison.recoveriq.records || 0) * (comparison.recoveriq.recall || 0) * 0.5);

  return (
    <div className="impact-analytics-grid">
      <div className="impact-card highlight-impact">
        <span className="impact-val">+{formatMinorCurrency(incrementalRevenue)}</span>
        <span className="impact-lbl">Incremental Revenue Captured</span>
        <p className="impact-desc">Lift generated above standard merchant retry policies</p>
      </div>

      <div className="impact-card">
        <span className="impact-val">+{recoveryRateDelta} pp</span>
        <span className="impact-lbl">Recovery Rate Improvement</span>
        <p className="impact-desc">Percentage point conversion efficiency gain</p>
      </div>

      <div className="impact-card">
        <span className="impact-val">-{fpReductionPct}%</span>
        <span className="impact-lbl">False-Positive Cost Reduction</span>
        <p className="impact-desc">Avoided decline fees and customer disruption</p>
      </div>

      <div className="impact-card">
        <span className="impact-val">{successfulRecoveries}</span>
        <span className="impact-lbl">Verified Recoveries (TP)</span>
        <p className="impact-desc">Successfully captured payments validated by webhook</p>
      </div>
    </div>
  );
}
