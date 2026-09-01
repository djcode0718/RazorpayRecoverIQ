import { FailureScenario } from "../../types";
import { Badge } from "../common/Badge";

type FailureScenariosListProps = {
  scenarios: FailureScenario[];
  expandedId: string | null;
  activeScenarioId?: string | null;
  onToggleExpand: (id: string) => void;
  onTrigger: (id: string) => void;
  isTriggering?: boolean;
};

export function FailureScenariosList({
  scenarios,
  expandedId,
  activeScenarioId,
  onToggleExpand,
  onTrigger,
  isTriggering = false,
}: FailureScenariosListProps) {
  return (
    <div className="scenarios-list-column">
      <div className="column-title-row">
        <h3>Interactive Failure & Resilience Scenarios</h3>
        <span className="badge badge-neutral badge-sm">{scenarios.length} Scenarios Available</span>
      </div>

      <div className="scenarios-list">
        {scenarios.map((scenario) => {
          const isExpanded = expandedId === scenario.scenario_id;
          const isRunning = activeScenarioId === scenario.scenario_id;
          const severityTone = scenario.severity.toUpperCase().includes("HIGH")
            ? "bad"
            : scenario.severity.toUpperCase().includes("MED")
            ? "warn"
            : "neutral";

          return (
            <div
              key={scenario.scenario_id}
              className={`scenario-card ${isExpanded ? "expanded" : ""} ${isRunning ? "active-run" : ""}`}
              onClick={() => onToggleExpand(scenario.scenario_id)}
              tabIndex={0}
              role="button"
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onToggleExpand(scenario.scenario_id);
                }
              }}
            >
              <div className="scenario-card-header">
                <div className="title-area">
                  <span className="scenario-expand-arrow">{isExpanded ? "▼" : "▶"}</span>
                  <div className="title-text-group">
                    <strong>{scenario.title}</strong>
                    <span className="scenario-id-tag font-mono">{scenario.scenario_id}</span>
                  </div>
                </div>
                <div className="actions-area" onClick={(e) => e.stopPropagation()}>
                  <Badge text={scenario.severity} tone={severityTone} size="sm" />
                  <button
                    onClick={() => onTrigger(scenario.scenario_id)}
                    disabled={isTriggering}
                    className="btn btn-primary btn-sm btn-trigger-scenario"
                    title={`Trigger ${scenario.title} live failure probe`}
                  >
                    Trigger Probe
                  </button>
                </div>
              </div>

              {isExpanded && (
                <div className="scenario-card-body">
                  <p className="scenario-desc-full">{scenario.description}</p>
                  <div className="detail-meta-grid">
                    <div>
                      <span className="detail-meta-label">TRIGGER CONDITION</span>
                      <p className="detail-meta-val">{scenario.trigger || "Simulated API trigger response."}</p>
                    </div>
                    <div>
                      <span className="detail-meta-label">EXPECTED BEHAVIOR</span>
                      <p className="detail-meta-val">{scenario.expected_behavior}</p>
                    </div>
                    <div>
                      <span className="detail-meta-label">ACTUAL BEHAVIOR</span>
                      <p className="detail-meta-val">{scenario.actual_behavior}</p>
                    </div>
                    <div>
                      <span className="detail-meta-label">SAFETY OUTCOME</span>
                      <p className="detail-meta-val outcome-text-badge">
                        {scenario.system_outcome || "Recovery blocked safely"}
                      </p>
                    </div>
                    <div className="full-width-meta">
                      <span className="detail-meta-label">AUDIT LEDGER RESULT</span>
                      <p className="detail-meta-val font-mono">{scenario.audit_result || "Audit event written to log."}</p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
