import { OperatingStatus } from "../../types";
import { Badge } from "../common/Badge";

type ReliabilityHeroProps = {
  operatingStatus?: OperatingStatus;
};

export function ReliabilityHero({ operatingStatus }: ReliabilityHeroProps) {
  const isHmacActive = operatingStatus?.webhook === "CONFIGURED" || operatingStatus?.webhook === "VERIFIED";
  const isPolicyActive = operatingStatus?.policy_engine === "ACTIVE";

  return (
    <div className="panel reliability-hero-panel">
      <div className="panel-header-with-badge">
        <div>
          <span className="section-step-tag">ENTERPRISE TRUST ARCHITECTURE</span>
          <h2>Platform Reliability & Cryptographic Security</h2>
          <p className="panel-copy">
            Evidence-driven validation demonstrating HMAC-SHA256 signature verification, event idempotency, fail-safe heuristics, and deterministic policy guardrails.
          </p>
        </div>
        <Badge text="ENTERPRISE SECURITY POSTURE" tone="good" size="sm" />
      </div>

      {/* 4 Trust Summary Cards */}
      <div className="trust-summary-4grid">
        <div className="trust-card">
          <div className="trust-head">
            <span className="trust-icon">⚡</span>
            <span className="trust-lbl">RELIABILITY</span>
          </div>
          <strong className="trust-val">Fail-Safe Active</strong>
          <span className="trust-sub">Autonomous heuristic fallback on API timeout</span>
        </div>

        <div className="trust-card">
          <div className="trust-head">
            <span className="trust-icon">🔒</span>
            <span className="trust-lbl">SECURITY</span>
          </div>
          <strong className="trust-val text-good">
            {isHmacActive ? "HMAC-SHA256" : "Signature Enforced"}
          </strong>
          <span className="trust-sub">Raw byte stream cryptographic verification</span>
        </div>

        <div className="trust-card">
          <div className="trust-head">
            <span className="trust-icon">🛡️</span>
            <span className="trust-lbl">DATA INTEGRITY</span>
          </div>
          <strong className="trust-val text-primary">Idempotency Ledger</strong>
          <span className="trust-sub">Zero-state duplicate webhook deduplication</span>
        </div>

        <div className="trust-card">
          <div className="trust-head">
            <span className="trust-icon">📜</span>
            <span className="trust-lbl">AUDITABILITY</span>
          </div>
          <strong className="trust-val">
            {isPolicyActive ? "7/7 Policy Gates" : "Deterministic Rules"}
          </strong>
          <span className="trust-sub">Immutable audit log for every state transition</span>
        </div>
      </div>
    </div>
  );
}
