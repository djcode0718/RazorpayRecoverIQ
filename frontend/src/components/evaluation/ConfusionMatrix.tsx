import { EvaluationDrilldownResponse } from "../../types";
import { formatMinorCurrency } from "../../utils/formatters";

type ConfusionMatrixProps = {
  drilldown: NonNullable<EvaluationDrilldownResponse["data"]>;
};

export function ConfusionMatrix({ drilldown }: ConfusionMatrixProps) {
  const { tp, fp, fn, tn } = drilldown.confusion_matrix;
  const total = tp + fp + fn + tn || 1;

  const tpPct = Math.round((tp / total) * 100);
  const fpPct = Math.round((fp / total) * 100);
  const fnPct = Math.round((fn / total) * 100);
  const tnPct = Math.round((tn / total) * 100);

  return (
    <div className="panel confusion-matrix-panel">
      <div className="panel-header-with-badge">
        <div>
          <span className="section-step-tag">CLASSIFICATION MATRIX</span>
          <h3>Diagnostic Confusion Matrix (Holdout Test Split)</h3>
        </div>
        <span className="badge badge-neutral badge-sm">N = {total} Cases</span>
      </div>
      <p className="panel-copy">
        Classification distribution comparing actual ground-truth recovery viability against RecoverIQ predictions.
      </p>

      {/* Actual 2x2 Matrix Grid */}
      <div className="confusion-matrix-table-wrapper">
        <div className="matrix-top-header-row">
          <div className="matrix-corner-cell" />
          <div className="matrix-col-header">
            <strong>ACTUAL RECOVERABLE</strong>
            <span>Payment with recoverable intent</span>
          </div>
          <div className="matrix-col-header">
            <strong>ACTUAL UNRECOVERABLE</strong>
            <span>Hard fraud or terminal decline</span>
          </div>
        </div>

        {/* Row 1: Predicted Recoverable */}
        <div className="matrix-data-row">
          <div className="matrix-row-header">
            <strong>PREDICTED RECOVERABLE</strong>
            <span>Recovery link dispatched</span>
          </div>

          {/* TP */}
          <div className="matrix-cell-card cell-tp">
            <div className="matrix-cell-top">
              <span className="matrix-cell-tag">TRUE POSITIVES (TP)</span>
              <span className="matrix-cell-pct badge badge-good badge-sm">{tpPct}% of total</span>
            </div>
            <strong className="matrix-cell-count text-good">{tp} cases</strong>
            <p className="matrix-cell-desc">
              Correctly diagnosed as recoverable & revenue successfully captured.
            </p>
          </div>

          {/* FP */}
          <div className="matrix-cell-card cell-fp">
            <div className="matrix-cell-top">
              <span className="matrix-cell-tag">FALSE POSITIVES (FP)</span>
              <span className="matrix-cell-pct badge badge-bad badge-sm">{fpPct}% of total</span>
            </div>
            <strong className="matrix-cell-count text-bad">{fp} cases</strong>
            <p className="matrix-cell-desc">
              Unrecoverable declines mistakenly attempted; incurs gateway fees.
            </p>
          </div>
        </div>

        {/* Row 2: Predicted Unrecoverable */}
        <div className="matrix-data-row">
          <div className="matrix-row-header">
            <strong>PREDICTED UNRECOVERABLE</strong>
            <span>Safely blocked by policy</span>
          </div>

          {/* FN */}
          <div className="matrix-cell-card cell-fn">
            <div className="matrix-cell-top">
              <span className="matrix-cell-tag">FALSE NEGATIVES (FN)</span>
              <span className="matrix-cell-pct badge badge-warn badge-sm">{fnPct}% of total</span>
            </div>
            <strong className="matrix-cell-count text-warn">{fn} cases</strong>
            <p className="matrix-cell-desc">
              Potentially recoverable payments missed due to overly strict threshold.
            </p>
          </div>

          {/* TN */}
          <div className="matrix-cell-card cell-tn">
            <div className="matrix-cell-top">
              <span className="matrix-cell-tag">TRUE NEGATIVES (TN)</span>
              <span className="matrix-cell-pct badge badge-neutral badge-sm">{tnPct}% of total</span>
            </div>
            <strong className="matrix-cell-count">{tn} cases</strong>
            <p className="matrix-cell-desc">
              Unrecoverable declines safely blocked by 7/7 deterministic safety gates.
            </p>
          </div>
        </div>
      </div>

      {/* Economics Summary Footer */}
      <div className="matrix-footer-metrics">
        <div className="matrix-footer-item">
          <span className="foot-lbl">TOTAL INTERVENTION EXPENSE:</span>
          <strong className="foot-val font-mono">
            {formatMinorCurrency(drilldown.false_positive_cost.intervention_cost_minor)}
          </strong>
        </div>
        <div className="matrix-footer-item">
          <span className="foot-lbl">AVOIDED FALSE-POSITIVE EXPOSURE:</span>
          <strong className="foot-val font-mono text-good">
            {formatMinorCurrency(drilldown.false_positive_cost.financial_exposure_minor)}
          </strong>
        </div>
        <div className="matrix-footer-item">
          <span className="foot-lbl">NET RECOVERED YIELD:</span>
          <strong className="foot-val font-mono text-good">
            {formatMinorCurrency(drilldown.summary.net_recovered_minor)}
          </strong>
        </div>
      </div>
    </div>
  );
}
