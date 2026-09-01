import { DashboardEvent } from "../../types";
import { formatTimeOnly } from "../../utils/formatters";

type TechnicalIntegrationDetailsProps = {
  events: DashboardEvent[];
};

export function TechnicalIntegrationDetails({ events }: TechnicalIntegrationDetailsProps) {
  return (
    <div className="panel technical-integration-panel">
      <div className="panel-header-with-badge">
        <div>
          <span className="section-step-tag">INTEGRATION & AUDIT</span>
          <h3>Technical Integration Details & Event Ledger</h3>
        </div>
        <span className="badge badge-neutral badge-sm">Developer Reference</span>
      </div>
      <p className="panel-copy">
        Tunneling endpoints, webhook registration guidelines, and live cryptographic audit trace.
      </p>

      {/* 1. Tunneling & Webhook Setup Guide */}
      <details className="technical-details-accordion" open>
        <summary>
          <span>🌐 Razorpay Webhook Gateway & Tunneling Architecture</span>
          <span className="details-arrow">▾</span>
        </summary>
        <div className="details-content-box">
          <div className="tunnel-steps-grid">
            <div className="tunnel-step-box">
              <span className="step-num-circle">1</span>
              <div>
                <strong>Local Tunnel Launch</strong>
                <p>Run <code>ngrok http 8000</code> to forward public webhook traffic to backend port 8000.</p>
              </div>
            </div>
            <div className="tunnel-step-box">
              <span className="step-num-circle">2</span>
              <div>
                <strong>Webhook URL Registration</strong>
                <p>Register endpoint <code>https://&lt;tunnel-id&gt;.ngrok-free.app/api/v1/webhooks/razorpay</code> in Razorpay Dashboard.</p>
              </div>
            </div>
            <div className="tunnel-step-box">
              <span className="step-num-circle">3</span>
              <div>
                <strong>Secret Key Matching</strong>
                <p>Ensure <code>RAZORPAY_WEBHOOK_SECRET</code> in <code>.env</code> matches Razorpay dashboard secret exactly.</p>
              </div>
            </div>
          </div>
        </div>
      </details>

      {/* 2. Audit Trail Events */}
      <details className="technical-details-accordion mt-md" open>
        <summary>
          <span>📜 Live Cryptographic Audit Trace Log</span>
          <span className="details-arrow">▾</span>
        </summary>
        <div className="details-content-box">
          <div className="audit-timeline-container">
            {events.length > 0 ? (
              events.slice(0, 8).map((evt) => (
                <div key={evt.id} className="audit-item">
                  <span className="audit-dot" />
                  <div className="audit-head">
                    <span className="audit-event-type font-mono">{evt.event_type}</span>
                    <span className="audit-time">{formatTimeOnly(evt.created_at)}</span>
                  </div>
                  <p className="audit-meta">
                    {evt.entity_type} {evt.entity_id} &bull; {evt.result || "PROCESSED"} &bull; {evt.reason || "Verified"}
                  </p>
                </div>
              ))
            ) : (
              <div className="audit-item">
                <span className="audit-dot" />
                <div className="audit-head">
                  <span className="audit-event-type">Audit System Idle</span>
                  <span className="audit-time">--:--</span>
                </div>
                <p className="audit-meta">Awaiting incoming webhook deliveries.</p>
              </div>
            )}
          </div>
        </div>
      </details>
    </div>
  );
}
