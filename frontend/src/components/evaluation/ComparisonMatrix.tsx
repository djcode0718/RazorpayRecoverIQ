import { EvaluationComparisonResponse } from "../../types";
import { formatMinorCurrency, formatPercentage } from "../../utils/formatters";

type ComparisonMatrixProps = {
  comparison: NonNullable<EvaluationComparisonResponse["data"]>;
};

export function ComparisonMatrix({ comparison }: ComparisonMatrixProps) {
  const { baseline, recoveriq } = comparison;

  const metrics = [
    {
      name: "Precision",
      desc: "Accuracy of predicted recoverable transactions without false attempts",
      recoveriq: formatPercentage(recoveriq.precision),
      baseline: formatPercentage(baseline.precision),
      delta: `${recoveriq.precision >= baseline.precision ? "+" : ""}${formatPercentage(recoveriq.precision - baseline.precision)}`,
      isBetter: recoveriq.precision >= baseline.precision,
    },
    {
      name: "Recall",
      desc: "Proportion of total recoverable payments successfully captured",
      recoveriq: formatPercentage(recoveriq.recall),
      baseline: formatPercentage(baseline.recall),
      delta: `${recoveriq.recall >= baseline.recall ? "+" : ""}${formatPercentage(recoveriq.recall - baseline.recall)}`,
      isBetter: recoveriq.recall >= baseline.recall,
    },
    {
      name: "F1 Quality Score",
      desc: "Harmonic mean balancing precision accuracy and recall coverage",
      recoveriq: formatPercentage(recoveriq.f1),
      baseline: formatPercentage(baseline.f1),
      delta: `${recoveriq.f1 >= baseline.f1 ? "+" : ""}${formatPercentage(recoveriq.f1 - baseline.f1)}`,
      isBetter: recoveriq.f1 >= baseline.f1,
    },
    {
      name: "Recovery Yield Rate",
      desc: "Gross revenue recovered divided by total recoverable exposure",
      recoveriq: formatPercentage(recoveriq.recovery_rate),
      baseline: formatPercentage(baseline.recovery_rate),
      delta: `${recoveriq.recovery_rate >= baseline.recovery_rate ? "+" : ""}${formatPercentage(recoveriq.recovery_rate - baseline.recovery_rate)}`,
      isBetter: recoveriq.recovery_rate >= baseline.recovery_rate,
    },
    {
      name: "Gross Recovered Revenue",
      desc: "Total capital successfully collected across holdout test set",
      recoveriq: formatMinorCurrency(recoveriq.gross_recovered_minor),
      baseline: formatMinorCurrency(baseline.gross_recovered_minor),
      delta: `+${formatMinorCurrency(Math.max(0, recoveriq.gross_recovered_minor - baseline.gross_recovered_minor))}`,
      isBetter: recoveriq.gross_recovered_minor >= baseline.gross_recovered_minor,
    },
    {
      name: "False-Positive Cost Exposure",
      desc: "Wasted retry fees and penalty charges on unrecoverable declines",
      recoveriq: formatMinorCurrency(recoveriq.false_positive_exposure_minor),
      baseline: formatMinorCurrency(baseline.false_positive_exposure_minor),
      delta: `-${formatMinorCurrency(Math.abs(baseline.false_positive_exposure_minor - recoveriq.false_positive_exposure_minor))}`,
      isBetter: recoveriq.false_positive_exposure_minor <= baseline.false_positive_exposure_minor,
    },
    {
      name: "Net Realized Capital",
      desc: "Gross recovered revenue minus total intervention execution costs",
      recoveriq: formatMinorCurrency(recoveriq.net_recovered_minor),
      baseline: formatMinorCurrency(baseline.net_recovered_minor),
      delta: `+${formatMinorCurrency(Math.max(0, recoveriq.net_recovered_minor - baseline.net_recovered_minor))}`,
      isBetter: recoveriq.net_recovered_minor >= baseline.net_recovered_minor,
    },
  ];

  return (
    <div className="panel comparison-matrix-panel">
      <div className="panel-header-with-badge">
        <div>
          <span className="section-step-tag">BENCHMARK COMPARISON</span>
          <h3>A/B Benchmark: RecoverIQ vs. Naive Payment Retries</h3>
        </div>
        <span className="badge badge-info badge-sm">Statistical A/B Validation</span>
      </div>
      <p className="panel-copy">
        Side-by-side performance benchmarking RecoverIQ AI policy-gate controls against naive baseline payment retries.
      </p>

      <div className="table-responsive">
        <table className="fintech-table comparison-table" role="table" aria-label="Evaluation Comparison Matrix">
          <thead>
            <tr>
              <th style={{ width: "34%" }}>Evaluation Metric</th>
              <th style={{ width: "22%" }}>RecoverIQ (AI Policy)</th>
              <th style={{ width: "22%" }}>Naive Baseline</th>
              <th style={{ width: "22%" }}>Improvement Delta</th>
            </tr>
          </thead>
          <tbody>
            {metrics.map((m) => (
              <tr key={m.name}>
                <td>
                  <strong className="metric-title">{m.name}</strong>
                  <span className="opp-secondary">{m.desc}</span>
                </td>
                <td>
                  <strong className="font-mono text-primary">{m.recoveriq}</strong>
                </td>
                <td className="font-mono text-soft">{m.baseline}</td>
                <td>
                  <span className={`badge ${m.isBetter ? "badge-good" : "badge-bad"} badge-sm`}>
                    {m.delta}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
