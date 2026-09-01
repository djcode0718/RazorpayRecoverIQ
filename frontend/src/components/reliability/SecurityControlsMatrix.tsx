import { Badge } from "../common/Badge";

export function SecurityControlsMatrix() {
  const controls = [
    {
      category: "Authentication",
      control: "API Key Authentication",
      status: "ENFORCED",
      evidence: "Bearer token & Razorpay key secret verified on all ingestion endpoints.",
      tone: "good" as const,
    },
    {
      category: "Authorization",
      control: "Action Guardrails & Approval",
      status: "ENFORCED",
      evidence: "Policy engine validates merchant authorization before payment link creation.",
      tone: "good" as const,
    },
    {
      category: "Cryptographic Integrity",
      control: "HMAC-SHA256 Signature Verification",
      status: "ENFORCED",
      evidence: "Raw byte stream computed digest compared against X-Razorpay-Signature header.",
      tone: "good" as const,
    },
    {
      category: "Idempotency",
      control: "Zero-State Deduplication Ledger",
      status: "ENFORCED",
      evidence: "Unique webhook event ID logged; duplicate delivery retries safely ignored.",
      tone: "good" as const,
    },
    {
      category: "Auditability",
      control: "Immutable Cryptographic Event Store",
      status: "ENFORCED",
      evidence: "Append-only database ledger recording timestamp, actor, entity ID, and result.",
      tone: "good" as const,
    },
    {
      category: "Data Validation",
      control: "Strict Schema & Type Validation",
      status: "ENFORCED",
      evidence: "Pydantic models reject malformed payloads with zero silent type coercion.",
      tone: "good" as const,
    },
    {
      category: "Fail-Safe Resilience",
      control: "Deterministic Heuristic Fallback",
      status: "ARMED",
      evidence: "Local rule engine immediately assumes classification on LLM timeout or error.",
      tone: "good" as const,
    },
  ];

  return (
    <div className="panel security-controls-panel">
      <div className="panel-header-with-badge">
        <div>
          <span className="section-step-tag">SECURITY CONTROLS</span>
          <h3>Verified Enterprise Security Controls</h3>
        </div>
        <span className="badge badge-good badge-sm">7/7 Controls Verified</span>
      </div>
      <p className="panel-copy">
        Deterministic security controls implemented to protect merchant revenue pipelines from duplicate charges, replay attacks, and unauthorized actions.
      </p>

      <div className="table-responsive">
        <table className="fintech-table controls-table" role="table" aria-label="Security Controls Matrix">
          <thead>
            <tr>
              <th style={{ width: "20%" }}>Category</th>
              <th style={{ width: "24%" }}>Security Control</th>
              <th style={{ width: "16%" }}>Enforcement</th>
              <th style={{ width: "40%" }}>Technical Evidence</th>
            </tr>
          </thead>
          <tbody>
            {controls.map((c) => (
              <tr key={c.control}>
                <td>
                  <span className="opp-secondary font-bold">{c.category}</span>
                </td>
                <td>
                  <strong className="metric-title">{c.control}</strong>
                </td>
                <td>
                  <Badge text={c.status} tone={c.tone} size="sm" />
                </td>
                <td>
                  <span className="control-evidence-text">{c.evidence}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
