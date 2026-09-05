import { useState } from "react";
import { parseNumber } from "../../utils/formatters";

type EvaluationRunFormProps = {
  isSubmitting: boolean;
  onSubmit: (params: {
    dataset_version: string;
    split: string;
    generation_seed: number;
    total_cases: number;
  }) => void;
};

export function EvaluationRunForm({ isSubmitting, onSubmit }: EvaluationRunFormProps) {
  const [datasetVersion, setDatasetVersion] = useState("default_dataset");
  const [split, setSplit] = useState("TEST");
  const [seed, setSeed] = useState("42");
  const [totalCases, setTotalCases] = useState("1000");
  const [isConfigOpen, setIsConfigOpen] = useState(false);

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    onSubmit({
      dataset_version: datasetVersion,
      split,
      generation_seed: parseNumber(seed, 42),
      total_cases: parseNumber(totalCases, 1000),
    });
  };

  return (
    <div className="evaluation-controls-wrapper">
      <div className="evaluation-controls-bar">
        <button
          type="button"
          className={`btn-toggle-config ${isConfigOpen ? "active" : ""}`}
          onClick={() => setIsConfigOpen(!isConfigOpen)}
          aria-expanded={isConfigOpen}
          title="Click to customize dataset version, split, seed, or test cases"
        >
          <span>⚙️ Benchmark Run Configuration &amp; Holdout Controls</span>
          <span className="details-arrow">{isConfigOpen ? "▴" : "▾"}</span>
        </button>

        <button
          type="button"
          disabled={isSubmitting}
          onClick={() => handleSubmit()}
          className="btn btn-primary btn-run-eval"
        >
          {isSubmitting ? "Running Benchmark..." : "Execute Evaluation Benchmark \u2192"}
        </button>
      </div>

      {isConfigOpen && (
        <form onSubmit={handleSubmit} className="evaluation-controls-form">
          <div className="field-block">
            <label htmlFor="eval-dataset">Dataset Version</label>
            <input
              id="eval-dataset"
              className="text-input"
              value={datasetVersion}
              onChange={(e) => setDatasetVersion(e.target.value)}
              placeholder="e.g. default_dataset"
            />
          </div>

          <div className="field-block">
            <label htmlFor="eval-split">Dataset Split</label>
            <select
              id="eval-split"
              className="select-input"
              value={split}
              onChange={(e) => setSplit(e.target.value)}
            >
              <option value="TEST">TEST (Unseen Production Holdout)</option>
              <option value="VALIDATION">VALIDATION (Tuning Set)</option>
              <option value="DEVELOPMENT">DEVELOPMENT (Training Sample)</option>
            </select>
          </div>

          <div className="field-block">
            <label htmlFor="eval-seed">Generation Seed</label>
            <input
              id="eval-seed"
              className="text-input"
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
              placeholder="42"
            />
          </div>

          <div className="field-block">
            <label htmlFor="eval-cases">Total Test Cases</label>
            <input
              id="eval-cases"
              className="text-input"
              value={totalCases}
              onChange={(e) => setTotalCases(e.target.value)}
              placeholder="1000"
            />
          </div>
        </form>
      )}
    </div>
  );
}

