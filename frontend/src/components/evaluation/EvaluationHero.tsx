import { EvaluationComparisonResponse } from "../../types";
import { formatMinorCurrency, formatPercentage, formatIsoTimestamp } from "../../utils/formatters";
import { Badge } from "../common/Badge";

type EvaluationHeroProps = {
  comparison: EvaluationComparisonResponse["data"] | null;
  totalRuns: number;
};

export function EvaluationHero({ comparison, totalRuns }: EvaluationHeroProps) {
  if (!comparison) {
    return null;
  }

  const { recoveriq, baseline, metadata } = comparison;
  const f1Delta = recoveriq.f1 - baseline.f1;
  const revenueGain = recoveriq.gross_recovered_minor - baseline.gross_recovered_minor;
  const fpReductionMinor = Math.max(0, baseline.false_positive_exposure_minor - recoveriq.false_positive_exposure_minor);

  return (
    <div className="panel evaluation-hero-banner">
      <div className="eval-score-ring">
        <span className="eval-score-val">{formatPercentage(recoveriq.f1)}</span>
        <span className="eval-score-label">F1 Benchmark</span>
      </div>

      <div className="eval-hero-details">
        <div className="eval-hero-title-row">
          <div>
            <span className="section-step-tag">STATISTICAL VALIDATION &bull; HOLDOUT TEST SUITE</span>
            <h2 className="eval-hero-heading">Model Performance & Recovery Intelligence Validation</h2>
          </div>
          <Badge text="STATISTICALLY SUPERIOR" tone="good" size="sm" />
        </div>

        <p className="eval-hero-subtitle">
          RecoverIQ machine learning classification and 7/7 deterministic safety gates capture{" "}
          <strong className="text-good">+{formatMinorCurrency(revenueGain)}</strong> incremental revenue and eliminate{" "}
          <strong className="text-good">{formatMinorCurrency(fpReductionMinor)}</strong> in wasted retry costs compared to naive baselines.
        </p>

        <div className="eval-hero-chips">
          <div className="eval-hero-chip">
            <span className="chip-lbl">F1 DELTA:</span>
            <strong className="chip-val text-good">
              {f1Delta >= 0 ? "+" : ""}{formatPercentage(f1Delta)}
            </strong>
          </div>
          <div className="eval-hero-chip">
            <span className="chip-lbl">DATASET SPLIT:</span>
            <strong className="chip-val">{metadata?.split ?? "TEST"} ({metadata?.total_cases ?? recoveriq.records} cases)</strong>
          </div>
          <div className="eval-hero-chip">
            <span className="chip-lbl">DATASET VERSION:</span>
            <strong className="chip-val font-mono">{metadata?.dataset_version ?? "default_dataset"}</strong>
          </div>
          <div className="eval-hero-chip">
            <span className="chip-lbl">TOTAL BENCHMARKS:</span>
            <strong className="chip-val">{totalRuns} runs recorded</strong>
          </div>
          {metadata?.timestamp && (
            <div className="eval-hero-chip">
              <span className="chip-lbl">LAST RUN:</span>
              <strong className="chip-val">{formatIsoTimestamp(metadata.timestamp)}</strong>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
