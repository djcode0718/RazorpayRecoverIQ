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

type ResilienceMonitorProps = {
  activeScenario: ActiveScenario | null;
  statusResult: string;
  error: string | null;
};

export function ResilienceMonitor({ activeScenario, statusResult, error }: ResilienceMonitorProps) {
  return (
    <div className="resilience-telemetry-column panel">
      <div className="telemetry-column-header">
        <h3>Active Simulation Monitor</h3>
        <Badge
          text={activeScenario ? "LIVE TELEMETRY TRACE" : "MONITOR IDLE"}
          tone={activeScenario ? "info" : "neutral"}
          size="sm"
        />
      </div>

      {error && <div className="execution-message-banner error">Error: {error}</div>}
      {statusResult && <div className="execution-message-banner success">Audit Verdict: {statusResult}</div>}

      {activeScenario ? (
        <div className="active-simulation-display">
          <div className="active-scenario-info">
            <span className="monitor-badge">PROBED ARCHETYPE</span>
            <h4>{activeScenario.title}</h4>
            {activeScenario.error_code && (
              <div className="scenario-error-header">
                <code>Expected Error Code: {activeScenario.error_code}</code>
              </div>
            )}
          </div>

          {/* 1. Custom Visual for Invalid Webhook Signature */}
          {activeScenario.scenario_id === "invalid_webhook_signature" ? (
            <div className="custom-visual-flow signature-flow">
              <h5>Cryptographic HMAC-SHA256 Verification Flow</h5>
              <div className="flow-steps-vert">
                <div className="flow-step-item pass">
                  <span className="flow-bullet">1</span>
                  <div className="flow-step-desc">
                    <strong>Webhook Payload Ingested</strong>
                    <span>Received raw byte stream from Razorpay gateway</span>
                  </div>
                </div>
                <div className="flow-step-arrow">↓</div>
                <div className="flow-step-item fail">
                  <span className="flow-bullet">✕</span>
                  <div className="flow-step-desc">
                    <strong>HMAC Signature Verification</strong>
                    <span>Calculated digest does NOT match header signature</span>
                  </div>
                </div>
                <div className="flow-step-arrow">↓</div>
                <div className="flow-step-item pass">
                  <span className="flow-bullet">✓</span>
                  <div className="flow-step-desc">
                    <strong>Rejection Response Sent</strong>
                    <span>Returned HTTP 401 Unauthorized securely</span>
                  </div>
                </div>
                <div className="flow-step-arrow">↓</div>
                <div className="flow-step-item block">
                  <span className="flow-bullet">✓</span>
                  <div className="flow-step-desc">
                    <strong>Zero Mutation Enforced</strong>
                    <span>Bypassed all database mutations and state machines</span>
                  </div>
                </div>
                <div className="flow-step-arrow">↓</div>
                <div className="flow-step-item audit">
                  <span className="flow-bullet">✓</span>
                  <div className="flow-step-desc">
                    <strong>Audit Ledger Written</strong>
                    <span>Security breach attempt logged in audit ledger</span>
                  </div>
                </div>
              </div>
              <div className="safety-outcome-box blocked">
                <strong>Safety Verdict:</strong> Recovery blocked safely &bull; Zero data corruption
              </div>
            </div>
          ) : activeScenario.scenario_id === "duplicate_webhook" ? (
            /* 2. Custom Visual for Duplicate Webhook Idempotency */
            <div className="custom-visual-flow duplicate-flow">
              <h5>Idempotency Ledger Verification</h5>
              <div className="duplicate-ledger-card">
                <div className="ledger-field">
                  <span className="field-label">EVENT ID</span>
                  <strong className="field-value font-mono">evt_demo_012_dup</strong>
                </div>
                <div className="ledger-events-timeline">
                  <div className="timeline-event item-processed">
                    <span className="event-dot pass" />
                    <div className="event-details">
                      <strong>Delivery #1 (Initial Event):</strong>
                      <span className="badge-processed">PROCESSED (200 OK)</span>
                      <span className="event-time">Timestamp: T-0</span>
                    </div>
                  </div>
                  <div className="timeline-event item-duplicate">
                    <span className="event-dot fail" />
                    <div className="event-details">
                      <strong>Delivery #2 (Duplicate Retry):</strong>
                      <span className="badge-duplicate">DUPLICATE DETECTED</span>
                      <span className="event-time">Timestamp: T+5s</span>
                    </div>
                  </div>
                </div>
                <div className="ledger-summary-row">
                  <div>
                    <span className="summary-label">ACTION TAKEN</span>
                    <strong className="summary-val text-bad font-mono">SAFELY IGNORED</strong>
                  </div>
                  <div>
                    <span className="summary-label">RECOVERY ATTEMPTS</span>
                    <strong className="summary-val text-good font-mono">EXACTLY 1</strong>
                  </div>
                </div>
              </div>
              <div className="safety-outcome-box safe">
                <strong>Safety Verdict:</strong> System remained safe &bull; Duplicate charge prevented
              </div>
            </div>
          ) : (
            /* 3. State Transition Pipeline */
            <div className="generic-resilience-pipeline">
              <h5>Autonomous State Transition Telemetry</h5>
              <div className="pipeline-steps-list">
                <div
                  className={`pipeline-step-node ${
                    activeScenario.state_transitions?.ai_provider === "pass"
                      ? "pass"
                      : activeScenario.state_transitions?.ai_provider === "fail"
                      ? "fail"
                      : "not_applicable"
                  }`}
                >
                  <span className="node-icon">
                    {activeScenario.state_transitions?.ai_provider === "fail" ? "✕" : "✓"}
                  </span>
                  <div className="node-label">
                    <strong>AI Provider Engine</strong>
                    <span>
                      {activeScenario.state_transitions?.ai_provider === "fail"
                        ? "Timeout / Unavailable (✕)"
                        : "Responded (✓)"}
                    </span>
                  </div>
                </div>

                <div
                  className={`pipeline-step-node ${
                    activeScenario.state_transitions?.fallback_activated === "pass" ? "pass" : "not_applicable"
                  }`}
                >
                  <span className="node-icon">
                    {activeScenario.state_transitions?.fallback_activated === "pass" ? "✓" : "N/A"}
                  </span>
                  <div className="node-label">
                    <strong>Deterministic Fallback</strong>
                    <span>
                      {activeScenario.state_transitions?.fallback_activated === "pass"
                        ? "Activated Safely (✓)"
                        : "Bypassed (N/A)"}
                    </span>
                  </div>
                </div>

                <div
                  className={`pipeline-step-node ${
                    activeScenario.state_transitions?.policy_evaluation === "pass"
                      ? "pass"
                      : activeScenario.state_transitions?.policy_evaluation === "fail"
                      ? "fail"
                      : "not_applicable"
                  }`}
                >
                  <span className="node-icon">
                    {activeScenario.state_transitions?.policy_evaluation === "fail" ? "✕" : "✓"}
                  </span>
                  <div className="node-label">
                    <strong>Deterministic Policy Evaluation</strong>
                    <span>
                      {activeScenario.state_transitions?.policy_evaluation === "fail"
                        ? "Policy Blocked (✕)"
                        : "Authorized (✓)"}
                    </span>
                  </div>
                </div>

                <div
                  className={`pipeline-step-node ${
                    activeScenario.state_transitions?.recovery === "pass"
                      ? "pass"
                      : activeScenario.state_transitions?.recovery === "fail"
                      ? "fail"
                      : "not_applicable"
                  }`}
                >
                  <span className="node-icon">
                    {activeScenario.state_transitions?.recovery === "fail" ? "✕" : "✓"}
                  </span>
                  <div className="node-label">
                    <strong>Recovery Action Execution</strong>
                    <span>
                      {activeScenario.state_transitions?.recovery === "fail"
                        ? "Action Failed (✕)"
                        : "Executed (✓)"}
                    </span>
                  </div>
                </div>

                <div
                  className={`pipeline-step-node ${
                    activeScenario.state_transitions?.verification === "pass"
                      ? "pass"
                      : activeScenario.state_transitions?.verification === "fail"
                      ? "fail"
                      : "not_applicable"
                  }`}
                >
                  <span className="node-icon">
                    {activeScenario.state_transitions?.verification === "fail" ? "✕" : "✓"}
                  </span>
                  <div className="node-label">
                    <strong>Outcome Verification</strong>
                    <span>
                      {activeScenario.state_transitions?.verification === "fail"
                        ? "Unverified / Pending (✕)"
                        : "Verified Success (✓)"}
                    </span>
                  </div>
                </div>
              </div>

              <div
                className={`safety-outcome-box ${
                  activeScenario.system_outcome?.toLowerCase().includes("safe") ? "safe" : "blocked"
                }`}
              >
                <strong>Safety Verdict:</strong> {activeScenario.system_outcome || "System remained safe"}
              </div>
            </div>
          )}

          <div className="telemetry-audit-card">
            <h5>Audit Event Trace Record</h5>
            <p className="font-mono">{activeScenario.audit_result}</p>
          </div>
        </div>
      ) : (
        <div className="empty-telemetry-monitor">
          <p>No active resilience simulation selected.</p>
          <span>Select any failure scenario from the left panel and click "Trigger Probe" to monitor live telemetry routing.</span>
        </div>
      )}
    </div>
  );
}
