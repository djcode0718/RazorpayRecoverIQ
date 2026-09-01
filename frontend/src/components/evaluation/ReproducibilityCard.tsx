import { EvaluationComparisonResponse } from "../../types";
import { formatIsoTimestamp } from "../../utils/formatters";
import { Badge } from "../common/Badge";

type ReproducibilityCardProps = {
  comparison: NonNullable<EvaluationComparisonResponse["data"]>;
};

export function ReproducibilityCard({ comparison }: ReproducibilityCardProps) {
  const metadata = comparison.metadata;

  return (
    <div className="panel reproducibility-card">
      <div className="panel-header-with-badge">
        <div>
          <span className="section-step-tag">PROVENANCE & TECHNICAL EVIDENCE</span>
          <h3>Audit Trail, Reproducibility & Decision Attribution</h3>
        </div>
        {metadata?.reproducible && <Badge text="DETERMINISTICALLY REPRODUCIBLE" tone="good" size="sm" />}
      </div>
      <p className="panel-copy">
        Cryptographic seed and dataset parameters for verifying benchmark scores independently without opaque assumptions.
      </p>

      {/* Metadata Grid */}
      {metadata && (
        <div className="metadata-grid-cols">
          <div className="meta-item">
            <span className="meta-lbl">DATASET VERSION</span>
            <strong className="meta-val font-mono">{metadata.dataset_version}</strong>
          </div>
          <div className="meta-item">
            <span className="meta-lbl">DATASET SPLIT</span>
            <strong className="meta-val">{metadata.split}</strong>
          </div>
          <div className="meta-item">
            <span className="meta-lbl">GENERATION SEED</span>
            <strong className="meta-val">{metadata.generation_seed ?? "42"}</strong>
          </div>
          <div className="meta-item">
            <span className="meta-lbl">TOTAL CASES AUDITED</span>
            <strong className="meta-val">{metadata.total_cases} cases</strong>
          </div>
          <div className="meta-item">
            <span className="meta-lbl">MODEL / STRATEGY</span>
            <strong className="meta-val">{metadata.model_strategy}</strong>
          </div>
          <div className="meta-item">
            <span className="meta-lbl">BENCHMARK RUN ID</span>
            <code className="meta-val font-mono">{metadata.run_id}</code>
          </div>
          <div className="meta-item full-col">
            <span className="meta-lbl">EXECUTION TIMESTAMP</span>
            <strong className="meta-val">{formatIsoTimestamp(metadata.timestamp)}</strong>
          </div>
        </div>
      )}

      {/* Progressive Disclosure: Technical Evidence & JSON Logs */}
      <details className="technical-details-accordion mt-md">
        <summary>
          <span>📜 View Raw Decision Attribution & Policy Deltas JSON</span>
          <span className="details-arrow">▾</span>
        </summary>
        <div className="details-content-box">
          <pre className="raw-json-block font-mono">
            {JSON.stringify(
              {
                attribution: comparison.attribution,
                deltas: comparison.deltas,
                comparison_note: comparison.comparison_note,
              },
              null,
              2
            )}
          </pre>
        </div>
      </details>
    </div>
  );
}
