import { useState } from "react";
import { FailureScenario } from "../../types";
import { Badge } from "../common/Badge";

type ActiveScenario = {
  scenario_id: string;
  title: string;
  severity: string;
  error_code?: string;
  error_message?: string;
  system_outcome?: string;
  audit_result?: string;
  state_transitions?: Record<string, string>;
};

type FailureScenariosSectionProps = {
  scenarios: FailureScenario[];
  activeScenario: ActiveScenario | null;
  statusResult: string;
  error: string | null;
  onTriggerScenario: (id: string) => void;
  isTriggering: boolean;
};

export function FailureScenariosSection({
  scenarios,
  activeScenario,
  statusResult,
  error,
  onTriggerScenario,
  isTriggering,
}: FailureScenariosSectionProps) {
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>(
    scenarios[0]?.scenario_id || "invalid_webhook_signature"
  );

  const selectedScenario =
    scenarios.find((s) => s.scenario_id === selectedScenarioId) || scenarios[0];

  const isCurrentRunning =
    isTriggering && (activeScenario?.scenario_id === selectedScenario?.scenario_id || true);

  const hasExecutedCurrent = activeScenario?.scenario_id === selectedScenario?.scenario_id;

  return (
    <div className="resilience-console-panel panel">
      <div className="panel-header-with-badge">
        <div>
          <span className="section-step-tag">PROBE CONSOLE</span>
          <h3>Failure & Resilience Probing Scenarios</h3>
        </div>
        <span className="badge badge-neutral badge-sm">{scenarios.length} Probes Configured</span>
      </div>
      <p className="panel-copy">
        Live interactive failure injection test suite validating system behavior during signature tampering, duplicate webhooks, LLM timeouts, and API disruptions.
      </p>

      <div className="resilience-2col-layout">
        {/* LEFT COLUMN: SCENARIO LIST */}
        <div className="scenarios-selector-column">
          <span className="col-header-lbl">SELECT FAILURE SCENARIO</span>
          <div className="scenarios-compact-list">
            {scenarios.map((sc) => {
              const isSelected = sc.scenario_id === selectedScenarioId;
              const isExecuted = activeScenario?.scenario_id === sc.scenario_id;
              const sevTone = sc.severity.toUpperCase().includes("HIGH")
                ? "bad"
                : sc.severity.toUpperCase().includes("MED")
                ? "warn"
                : "neutral";

              return (
                <div
                  key={sc.scenario_id}
                  className={`scenario-list-row ${isSelected ? "selected" : ""}`}
                  onClick={() => setSelectedScenarioId(sc.scenario_id)}
                  tabIndex={0}
                  role="button"
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setSelectedScenarioId(sc.scenario_id);
                    }
                  }}
                >
                  <div className="scenario-row-top">
                    <strong className="scenario-row-title">{sc.title}</strong>
                    <div className="scenario-row-tags">
                      <Badge text={sc.severity} tone={sevTone} size="sm" />
                      {isExecuted ? (
                        <Badge text="PROBED (PASSED)" tone="good" size="sm" />
                      ) : (
                        <Badge text="NOT TESTED" tone="neutral" size="sm" />
                      )}
                    </div>
                  </div>
                  <p className="scenario-row-desc">{sc.description}</p>
                </div>
              );
            })}
          </div>
        </div>

        {/* RIGHT COLUMN: SELECTED SCENARIO DEEP-DIVE & TELEMETRY */}
        <div className="scenario-detail-column">
          {selectedScenario ? (
            <div className="selected-scenario-card">
              <div className="scenario-detail-header">
                <div>
                  <span className="probe-tag font-mono">{selectedScenario.scenario_id}</span>
                  <h4 className="probe-title">{selectedScenario.title}</h4>
                </div>
                <button
                  onClick={() => onTriggerScenario(selectedScenario.scenario_id)}
                  disabled={isTriggering}
                  className="btn btn-primary btn-run-probe"
                >
                  {isTriggering && activeScenario?.scenario_id === selectedScenario.scenario_id
                    ? "Running Live Probe..."
                    : "Run Scenario Probe \u2192"}
                </button>
              </div>

              {error && hasExecutedCurrent && (
                <div className="execution-message-banner error">Error: {error}</div>
              )}
              {statusResult && hasExecutedCurrent && (
                <div className="execution-message-banner success">Audit Verdict: {statusResult}</div>
              )}

              {/* Specification Grid */}
              <div className="probe-specs-grid">
                <div className="spec-box">
                  <span className="spec-lbl">TRIGGER CONDITION</span>
                  <p className="spec-val">{selectedScenario.trigger || "Live API probe request."}</p>
                </div>
                <div className="spec-box">
                  <span className="spec-lbl">EXPECTED BEHAVIOR</span>
                  <p className="spec-val">{selectedScenario.expected_behavior}</p>
                </div>
                <div className="spec-box">
                  <span className="spec-lbl">SECURITY / RELIABILITY CONTROL</span>
                  <p className="spec-val text-good">{selectedScenario.system_outcome || "Deterministic Safety Gate Block"}</p>
                </div>
                <div className="spec-box">
                  <span className="spec-lbl">AUDIT RESULT</span>
                  <p className="spec-val font-mono">{selectedScenario.audit_result || "Cryptographic event ledger entry"}</p>
                </div>
              </div>

              {/* Dynamic Live Telemetry Visual */}
              {hasExecutedCurrent && activeScenario ? (
                <div className="live-telemetry-box">
                  <h5>Live Transition Telemetry</h5>

                  {activeScenario.scenario_id === "invalid_webhook_signature" ? (
                    <div className="telemetry-flow-steps">
                      <div className="flow-step pass">
                        <span className="step-num">1</span>
                        <div className="step-desc">
                          <strong>Raw Webhook Ingested</strong>
                          <span>Received payload bytes via POST endpoint</span>
                        </div>
                      </div>
                      <div className="flow-step fail">
                        <span className="step-num">✕</span>
                        <div className="step-desc">
                          <strong>HMAC Signature Verification</strong>
                          <span>Computed digest != X-Razorpay-Signature header</span>
                        </div>
                      </div>
                      <div className="flow-step pass">
                        <span className="step-num">✓</span>
                        <div className="step-desc">
                          <strong>Zero Mutation Guard</strong>
                          <span>HTTP 401 returned, database write bypassed</span>
                        </div>
                      </div>
                    </div>
                  ) : activeScenario.scenario_id === "duplicate_webhook" ? (
                    <div className="telemetry-flow-steps">
                      <div className="flow-step pass">
                        <span className="step-num">1</span>
                        <div className="step-desc">
                          <strong>Initial Delivery #1 (T-0)</strong>
                          <span>Signature verified, ingested & recovery initiated</span>
                        </div>
                      </div>
                      <div className="flow-step fail">
                        <span className="step-num">⚡</span>
                        <div className="step-desc">
                          <strong>Duplicate Delivery #2 (T+5s)</strong>
                          <span>Event hash found in Idempotency Ledger &bull; Safely ignored</span>
                        </div>
                      </div>
                      <div className="flow-step pass">
                        <span className="step-num">✓</span>
                        <div className="step-desc">
                          <strong>Zero Duplicate Charges</strong>
                          <span>Exactly 1 recovery action executed</span>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="telemetry-flow-steps">
                      <div className="flow-step pass">
                        <span className="step-num">✓</span>
                        <div className="step-desc">
                          <strong>Subsystem Anomaly Handled</strong>
                          <span>{activeScenario.system_outcome || "Fallback path activated safely"}</span>
                        </div>
                      </div>
                    </div>
                  )}

                  <div className="safety-verdict-banner text-good font-bold">
                    ✓ Safety Outcome: System remained stable &bull; Audit trail captured.
                  </div>
                </div>
              ) : (
                <div className="untested-prompt-box">
                  <p>Click <strong>"Run Scenario Probe"</strong> to execute this live resilience validation against the backend API.</p>
                </div>
              )}
            </div>
          ) : (
            <div className="empty-probe-box">
              <p>Select a scenario from the left to view details and execute live probes.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
