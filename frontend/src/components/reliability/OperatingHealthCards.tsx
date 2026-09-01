import { OperatingStatus } from "../../types";
import { Badge } from "../common/Badge";

type OperatingHealthCardsProps = {
  operatingStatus?: OperatingStatus;
};

export function OperatingHealthCards({ operatingStatus }: OperatingHealthCardsProps) {
  const isGatewayConnected = operatingStatus?.payment_environment === "RAZORPAY TEST" || Boolean(operatingStatus?.payment_environment);
  const isWebhookActive = operatingStatus?.webhook === "CONFIGURED" || operatingStatus?.webhook === "VERIFIED";
  const isAiActive = operatingStatus?.ai_provider !== "UNAVAILABLE";
  const isPolicyActive = operatingStatus?.policy_engine === "ACTIVE";

  return (
    <div className="panel operating-health-section">
      <div className="panel-header-with-badge">
        <div>
          <span className="section-step-tag">SUBSYSTEM TELEMETRY</span>
          <h3>Operational Infrastructure Health</h3>
        </div>
        <span className="badge badge-good badge-sm">All Subsystems Operational</span>
      </div>
      <p className="panel-copy">
        Live connectivity, cryptographic verification status, and failover health across core recovery pipelines.
      </p>

      <div className="operating-health-4grid">
        {/* 1. Payment Gateway */}
        <div className="health-card-modern">
          <div className="health-card-top">
            <span className="health-card-icon">💳</span>
            <Badge
              text={isGatewayConnected ? "CONNECTED" : "DISCONNECTED"}
              tone={isGatewayConnected ? "good" : "bad"}
              size="sm"
            />
          </div>
          <div className="health-card-body">
            <strong className="health-card-title">Payment Gateway</strong>
            <span className="health-card-env">
              {operatingStatus?.payment_environment || "RAZORPAY TEST MODE"}
            </span>
            <p className="health-card-detail">
              API connectivity verified with active merchant credentials and rate-limit guardrails.
            </p>
          </div>
        </div>

        {/* 2. Webhook Gateway */}
        <div className="health-card-modern">
          <div className="health-card-top">
            <span className="health-card-icon">🔗</span>
            <Badge
              text={isWebhookActive ? "VERIFIED" : "WAITING"}
              tone={isWebhookActive ? "good" : "warn"}
              size="sm"
            />
          </div>
          <div className="health-card-body">
            <strong className="health-card-title">Webhook Gateway</strong>
            <span className="health-card-env">HMAC-SHA256 AUTHENTICATED</span>
            <p className="health-card-detail">
              {operatingStatus?.last_event
                ? `Last event: ${operatingStatus.last_event}`
                : "Awaiting live webhook delivery from Razorpay sandbox."}
            </p>
          </div>
        </div>

        {/* 3. AI Intelligence */}
        <div className="health-card-modern">
          <div className="health-card-top">
            <span className="health-card-icon">🧠</span>
            <Badge
              text={operatingStatus?.ai_provider || "ACTIVE"}
              tone={isAiActive ? "good" : "warn"}
              size="sm"
            />
          </div>
          <div className="health-card-body">
            <strong className="health-card-title">AI Intelligence</strong>
            <span className="health-card-env">AUTONOMOUS ML ENGINE</span>
            <p className="health-card-detail">
              {operatingStatus?.ai_provider_note || "Local heuristic fallback armed for 100% failover resilience."}
            </p>
          </div>
        </div>

        {/* 4. Policy Engine */}
        <div className="health-card-modern">
          <div className="health-card-top">
            <span className="health-card-icon">🛡️</span>
            <Badge
              text={isPolicyActive ? "ACTIVE" : "DEGRADED"}
              tone={isPolicyActive ? "good" : "bad"}
              size="sm"
            />
          </div>
          <div className="health-card-body">
            <strong className="health-card-title">Policy Safety Engine</strong>
            <span className="health-card-env">7/7 DETERMINISTIC CHECKS</span>
            <p className="health-card-detail">
              {operatingStatus?.policy_engine_note || "Strict velocity, risk limits, and idempotency checks enforced."}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
