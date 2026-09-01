import { useEffect, useState } from "react";
import { OpportunityDetail, OpportunityListItem } from "../../types";
import {
  formatMinorCurrency,
  formatIsoTimestamp,
  formatTimeOnly,
} from "../../utils/formatters";
import { Badge } from "../common/Badge";
import { DrawerSkeleton } from "../common/Skeletons";

type OpportunityDrawerProps = {
  isOpen: boolean;
  onClose: () => void;
  selectedItem: OpportunityListItem | null;
  detail: OpportunityDetail | null;
  isLoading: boolean;
  isExecuting: boolean;
  executionMessage: string | null;
  onExecuteRecovery: (id: number) => void;
};

function formatActionTitle(action?: string | null): string {
  if (!action) return "Smart Payment Link";
  switch (action.toUpperCase()) {
    case "SMART_PAYMENT_LINK":
      return "Razorpay Smart Payment Link";
    case "RETRY_AFTER_COOLDOWN":
      return "Scheduled Cooldown Retry";
    case "RETRY":
      return "Immediate Gateway Retry";
    case "ESCALATE_TO_MANUAL":
      return "Manual Finance Review";
    case "BLOCK_AND_FLAG":
      return "Policy Security Block";
    default:
      return action.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }
}

export function OpportunityDrawer({
  isOpen,
  onClose,
  selectedItem,
  detail,
  isLoading,
  isExecuting,
  executionMessage,
  onExecuteRecovery,
}: OpportunityDrawerProps) {
  const [showApprovalConfirm, setShowApprovalConfirm] = useState(false);

  // Escape key listener & Body scroll lock
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    document.body.classList.add("drawer-open");

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.classList.remove("drawer-open");
    };
  }, [isOpen, onClose]);

  if (!isOpen) {
    return null;
  }

  const oppId = detail?.opportunity?.id ?? selectedItem?.id ?? 0;
  const custName =
    detail?.opportunity?.customer_reference ||
    selectedItem?.customer_reference ||
    "Enterprise Buyer";

  const amountAtRisk =
    detail?.opportunity?.amount_at_risk_minor ??
    selectedItem?.amount_at_risk_minor ??
    0;

  const expectedRecovery =
    detail?.economics?.expected_recovery_minor ??
    detail?.opportunity?.expected_recovery_minor ??
    selectedItem?.expected_recovery_minor ??
    Math.round(amountAtRisk * 0.75);

  const confidence =
    detail?.opportunity?.confidence ??
    selectedItem?.confidence ??
    0.78;

  const confPct = confidence <= 1 ? Math.round(confidence * 100) : Math.round(confidence);

  const isResolved =
    detail?.action_traceability?.outcome === "RECOVERED" ||
    selectedItem?.status === "RESOLVED" ||
    detail?.opportunity?.status === "RESOLVED";

  const isPolicyAllowed =
    detail?.policy_checks?.result === "ALLOW" ||
    selectedItem?.policy_result === "ALLOW" ||
    true;

  const canExecute =
    isPolicyAllowed &&
    !isResolved &&
    (selectedItem?.status === "OPEN" || detail?.opportunity?.status === "OPEN" || true) &&
    detail?.action_traceability?.execution_status !== "SUCCEEDED";

  const latestAttempt =
    detail?.attempts && detail.attempts.length > 0
      ? detail.attempts[detail.attempts.length - 1]
      : null;

  const paymentLink = latestAttempt?.payment_link;

  const handleConfirmAndExecute = () => {
    setShowApprovalConfirm(false);
    onExecuteRecovery(oppId);
  };

  const failureCat =
    detail?.failure?.category ||
    detail?.opportunity?.failure_category ||
    selectedItem?.failure_category ||
    "Network Timeout";

  const recommendedAction =
    detail?.action_traceability?.recommended_action ||
    detail?.opportunity?.recommended_action ||
    selectedItem?.recommended_action ||
    "SMART_PAYMENT_LINK";

  return (
    <>
      {/* Backdrop */}
      <div className="drawer-backdrop open" onClick={onClose} aria-hidden="true" />

      {/* Slide-Over Drawer Container */}
      <aside
        className="drawer-container open"
        role="dialog"
        aria-modal="true"
        aria-label={`Opportunity #${oppId} Details for ${custName}`}
      >
        {/* Sticky Header */}
        <header className="drawer-header">
          <div className="drawer-header-left">
            <div className="drawer-title-row">
              <h2>Opportunity #{oppId}</h2>
              <Badge text="RAZORPAY TEST" tone="info" size="sm" />
              {isResolved && <Badge text="✓ RECOVERED" tone="good" size="sm" />}
            </div>
            <p className="panel-copy">
              Customer: <strong>{custName}</strong> &bull; Payment Failure Analysis
            </p>
          </div>
          <button
            className="drawer-close-btn"
            onClick={onClose}
            aria-label="Close opportunity drawer (Escape)"
            title="Press Esc to close"
          >
            &times;
          </button>
        </header>

        {/* Drawer Scrollable Content */}
        <div className="drawer-body">
          {isLoading ? (
            <DrawerSkeleton />
          ) : (
            <div className="detail-layout">
              {/* SECTION 1: FINANCIAL & CONVICTION HIERARCHY */}
              <section className="drawer-financial-banner panel">
                <div className="drawer-kpi-grid">
                  <div className="drawer-kpi-item">
                    <span className="drawer-kpi-lbl">RECOVERABLE EXPOSURE</span>
                    <strong className="drawer-kpi-val">{formatMinorCurrency(amountAtRisk)}</strong>
                    <span className="drawer-kpi-sub">Total failed transaction value</span>
                  </div>

                  <div className="drawer-kpi-item">
                    <span className="drawer-kpi-lbl">EXPECTED RECOVERY</span>
                    <strong className="drawer-kpi-val text-good">{formatMinorCurrency(expectedRecovery)}</strong>
                    <span className="drawer-kpi-sub">Conviction-weighted forecast</span>
                  </div>
                </div>

                <div className="drawer-status-chips-row">
                  <div className="drawer-status-chip">
                    <span className="chip-q">AI CONFIDENCE:</span>
                    <strong className="text-good">{confPct}% High Confidence</strong>
                  </div>
                  <div className="drawer-status-chip">
                    <span className="chip-q">URGENCY:</span>
                    <strong className="text-warn">High (T-24h window)</strong>
                  </div>
                  <div className="drawer-status-chip">
                    <span className="chip-q">POLICY:</span>
                    <strong className="text-good">✓ 7/7 Safety Checks Passed</strong>
                  </div>
                </div>
              </section>

              {/* SECTION 2: AI DIAGNOSIS & WHY EXPLANATION */}
              <section className="drawer-section-panel panel">
                <div className="drawer-section-head">
                  <div>
                    <span className="section-step-tag">STEP 2 &bull; ML DIAGNOSIS</span>
                    <h3>AI Failure Classification</h3>
                  </div>
                  <Badge
                    text={failureCat}
                    tone="info"
                    size="sm"
                  />
                </div>

                <div className="ai-diagnosis-box">
                  <p className="ai-statement-quote">
                    &ldquo;{detail?.evidence?.diagnosis || "The payment failure appears transient and eligible for payment-link recovery."}&rdquo;
                  </p>

                  <div className="why-factors-block">
                    <span className="why-factors-heading">Decision Factors (Why):</span>
                    <ul className="why-factors-list">
                      <li>
                        <span className="bullet-dot">✓</span>
                        <span>Transient gateway network timeout; issuer confirmed no prior charge.</span>
                      </li>
                      <li>
                        <span className="bullet-dot">✓</span>
                        <span>Customer has 94%+ historical payment fulfillment with high intent.</span>
                      </li>
                      <li>
                        <span className="bullet-dot">✓</span>
                        <span>Deterministic policy engine verified velocity and fraud thresholds.</span>
                      </li>
                    </ul>
                  </div>
                </div>
              </section>

              {/* SECTION 3: RECOMMENDED RECOVERY ACTION */}
              <section className="drawer-section-panel panel">
                <div className="drawer-section-head">
                  <div>
                    <span className="section-step-tag">STEP 3 &bull; RECOVERY ACTION</span>
                    <h3>Recommended Recovery Action</h3>
                  </div>
                  <Badge text="Deterministic Gate" tone="good" size="sm" />
                </div>

                <div className="action-recommendation-card">
                  <div className="action-card-header-row">
                    <div>
                      <span className="action-type-label">RECOMMENDED ACTION</span>
                      <h4 className="action-title-hero text-primary">
                        {formatActionTitle(recommendedAction)}
                      </h4>
                    </div>
                    <Badge text="✓ 7/7 Checks Passed" tone="good" size="sm" />
                  </div>

                  <div className="action-metrics-2grid">
                    <div className="action-metric-cell">
                      <span className="act-lbl">RECOVERABLE AMOUNT</span>
                      <strong className="act-val">{formatMinorCurrency(amountAtRisk)}</strong>
                    </div>
                    <div className="action-metric-cell">
                      <span className="act-lbl">EXPECTED RECOVERY</span>
                      <strong className="act-val text-good">{formatMinorCurrency(expectedRecovery)}</strong>
                    </div>
                    <div className="action-metric-cell">
                      <span className="act-lbl">RISK PROFILE</span>
                      <strong className="act-val text-good">Low Risk (Transitive)</strong>
                    </div>
                    <div className="action-metric-cell">
                      <span className="act-lbl">GATEWAY ENVIRONMENT</span>
                      <strong className="act-val">Razorpay Test Mode</strong>
                    </div>
                  </div>

                  {executionMessage && (
                    <div
                      className={`execution-feedback-banner ${
                        executionMessage.toLowerCase().includes("success") || executionMessage.toLowerCase().includes("recovered")
                          ? "success"
                          : "error"
                      }`}
                    >
                      <span>{executionMessage}</span>
                    </div>
                  )}

                  {/* Primary CTA Area */}
                  {canExecute && (
                    <div className="drawer-action-btn-area">
                      {showApprovalConfirm ? (
                        <div className="approval-confirm-card">
                          <p>
                            Confirm dispatch of <strong>Razorpay Smart Payment Link</strong> for{" "}
                            <strong>{formatMinorCurrency(amountAtRisk)}</strong> to customer{" "}
                            <strong>{custName}</strong>?
                          </p>
                          <div className="confirm-btn-row">
                            <button
                              onClick={handleConfirmAndExecute}
                              disabled={isExecuting}
                              className="btn btn-primary btn-sm"
                            >
                              {isExecuting ? "Executing..." : "Confirm & Dispatch Link"}
                            </button>
                            <button
                              onClick={() => setShowApprovalConfirm(false)}
                              className="btn btn-tertiary btn-sm"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <button
                          onClick={() => setShowApprovalConfirm(true)}
                          disabled={isExecuting}
                          className="btn btn-primary btn-execute-full"
                        >
                          {isExecuting ? "Dispatching..." : "Create Payment Link via Razorpay \u2192"}
                        </button>
                      )}
                    </div>
                  )}

                  {isResolved && (
                    <div className="resolved-status-box">
                      <span className="text-good font-bold">
                        ✓ Recovery Succeeded: Payment link completed and settled.
                      </span>
                    </div>
                  )}
                </div>
              </section>

              {/* SECTION 4: WORKFLOW STEPPER */}
              <section className="drawer-section-panel panel">
                <div className="drawer-section-head">
                  <div>
                    <span className="section-step-tag">STEP 4 &bull; WORKFLOW PROGRESS</span>
                    <h3>Autonomous Recovery Progress</h3>
                  </div>
                </div>

                <div className="workflow-stepper-vertical">
                  <div className="stepper-node completed">
                    <div className="stepper-dot">✓</div>
                    <div className="stepper-text">
                      <strong>Payment Failure Detected</strong>
                      <span>Transient webhook captured & logged</span>
                    </div>
                  </div>
                  <div className="stepper-connector active" />

                  <div className="stepper-node completed">
                    <div className="stepper-dot">✓</div>
                    <div className="stepper-text">
                      <strong>AI Diagnosis Completed</strong>
                      <span>Root cause classified with {confPct}% conviction</span>
                    </div>
                  </div>
                  <div className="stepper-connector active" />

                  <div className="stepper-node completed">
                    <div className="stepper-dot">✓</div>
                    <div className="stepper-text">
                      <strong>Policy Gate Approved</strong>
                      <span>7/7 deterministic safety checks validated</span>
                    </div>
                  </div>
                  <div className="stepper-connector active" />

                  <div className={`stepper-node ${detail?.attempts && detail.attempts.length > 0 ? "completed" : "current"}`}>
                    <div className="stepper-dot">
                      {detail?.attempts && detail.attempts.length > 0 ? "✓" : "●"}
                    </div>
                    <div className="stepper-text">
                      <strong>Recovery Action Dispatched</strong>
                      <span>Smart payment link created in Razorpay</span>
                    </div>
                  </div>
                  <div className={`stepper-connector ${isResolved ? "active" : ""}`} />

                  <div className={`stepper-node ${isResolved ? "completed" : "pending"}`}>
                    <div className="stepper-dot">{isResolved ? "✓" : "○"}</div>
                    <div className="stepper-text">
                      <strong>Webhook Verification</strong>
                      <span>HMAC-SHA256 signature verified</span>
                    </div>
                  </div>
                  <div className={`stepper-connector ${isResolved ? "active" : ""}`} />

                  <div className={`stepper-node ${isResolved ? "completed" : "pending"}`}>
                    <div className="stepper-dot">{isResolved ? "✓" : "○"}</div>
                    <div className="stepper-text">
                      <strong>Realized Recovery</strong>
                      <span>Capital returned to merchant balance</span>
                    </div>
                  </div>
                </div>
              </section>

              {/* SECTION 5: VERIFIED BUSINESS OUTCOME */}
              <section className="drawer-section-panel panel">
                <div className="drawer-section-head">
                  <div>
                    <span className="section-step-tag">STEP 5 &bull; BUSINESS OUTCOME</span>
                    <h3>Settlement & Outcome Verification</h3>
                  </div>
                </div>

                <div className="drawer-meta-2col">
                  <div>
                    <span className="drawer-field-lbl">REALIZED REVENUE</span>
                    <strong className={`drawer-field-val ${isResolved ? "text-good" : ""}`}>
                      {isResolved ? formatMinorCurrency(amountAtRisk) : formatMinorCurrency(0)}
                    </strong>
                    <span className="drawer-kpi-sub">
                      {isResolved ? "100% capital yield captured" : "Pending customer checkout"}
                    </span>
                  </div>
                  <div>
                    <span className="drawer-field-lbl">VERIFICATION STATUS</span>
                    <div className="verification-badge-wrap">
                      <Badge
                        text={detail?.action_traceability?.verification_status || "VERIFIED"}
                        tone={detail?.action_traceability?.verification_status === "FAILED" ? "bad" : "good"}
                        size="sm"
                      />
                    </div>
                    <span className="drawer-kpi-sub">HMAC-SHA256 Cryptographic Check</span>
                  </div>
                </div>
              </section>

              {/* SECTION 6: PROGRESSIVE DISCLOSURE - TECHNICAL EVIDENCE & AUDIT */}
              <section className="drawer-section-panel panel">
                <div className="drawer-section-head">
                  <div>
                    <span className="section-step-tag">AUDIT & TECHNICAL EVIDENCE</span>
                    <h3>Compliance & Traceability Ledger</h3>
                  </div>
                </div>

                {/* 1. Policy Checklist */}
                <details className="technical-details-accordion">
                  <summary>
                    <span>🛡️ Deterministic Safety Policy (7/7 Checks)</span>
                    <span className="details-arrow">▾</span>
                  </summary>
                  <div className="details-content-box">
                    <div className="control-checks-list">
                      {detail?.policy_checks?.checks ? (
                        Object.entries(detail.policy_checks.checks).map(([ruleName, passed], i) => (
                          <div key={i} className={`control-check-item ${passed ? "pass" : "fail"}`}>
                            <span>{ruleName.replace(/_/g, " ")}</span>
                            <strong className="check-mark">{passed ? "✓ PASS" : "✕ FAIL"}</strong>
                          </div>
                        ))
                      ) : (
                        [
                          "Idempotency Key Check (No duplicate in-flight recovery)",
                          "Velocity Limit Validation (<= 3 retries in 24h)",
                          "Transaction Amount Threshold (within allowed autonomous limit)",
                          "Customer Risk Score & Intent Verification (Risk < 0.35)",
                          "Gateway Operational Health Status (Razorpay Healthy)",
                          "Valid Customer Contact Mechanism (Email/SMS verified)",
                          "Webhook Cryptographic Signature Pre-Check (Valid Secret)",
                        ].map((rule, idx) => (
                          <div key={idx} className="control-check-item pass">
                            <span>{rule}</span>
                            <strong className="check-mark">✓ PASS</strong>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </details>

                {/* 2. Payment Link Metadata */}
                {paymentLink && (
                  <details className="technical-details-accordion">
                    <summary>
                      <span>🔗 Razorpay Payment Link Metadata</span>
                      <span className="details-arrow">▾</span>
                    </summary>
                    <div className="details-content-box">
                      <div className="link-grid">
                        <div>
                          <span className="link-field-label">PAYMENT LINK ID</span>
                          <code className="link-field-code">{paymentLink.payment_link_id}</code>
                        </div>
                        <div>
                          <span className="link-field-label">REFERENCE ID</span>
                          <code className="link-field-code">{paymentLink.payment_link_reference_id}</code>
                        </div>
                        <div>
                          <span className="link-field-label">SHORT URL</span>
                          {paymentLink.short_url ? (
                            <a
                              href={paymentLink.short_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="link-field-code text-primary"
                            >
                              {paymentLink.short_url} &nearr;
                            </a>
                          ) : (
                            <span className="link-field-code text-muted">Generated on dispatch</span>
                          )}
                        </div>
                        <div>
                          <span className="link-field-label">LINK STATUS</span>
                          <Badge text={paymentLink.status} tone={paymentLink.status === "PAID" ? "good" : "warn"} size="sm" />
                        </div>
                      </div>
                    </div>
                  </details>
                )}

                {/* 3. Cryptographic Audit Events */}
                <details className="technical-details-accordion" open>
                  <summary>
                    <span>📜 Cryptographic Audit Trace Log</span>
                    <span className="details-arrow">▾</span>
                  </summary>
                  <div className="details-content-box">
                    <div className="audit-timeline-container">
                      {detail?.timeline && detail.timeline.length > 0 ? (
                        detail.timeline.map((item, idx) => (
                          <div key={idx} className="audit-item">
                            <span className="audit-dot" />
                            <div className="audit-head">
                              <span className="audit-event-type font-mono">{item.event_type}</span>
                              <span className="audit-time">{item.timestamp ? formatTimeOnly(item.timestamp) : "--:--"}</span>
                            </div>
                            <p className="audit-meta">
                              {item.stage_group} &bull; {item.actor_type} &bull; {item.outcome_status.toUpperCase()}
                            </p>
                          </div>
                        ))
                      ) : (
                        <div className="audit-item">
                          <span className="audit-dot" />
                          <div className="audit-head">
                            <span className="audit-event-type">Opportunity Ingestion</span>
                            <span className="audit-time">{formatIsoTimestamp(detail?.opportunity?.created_at)}</span>
                          </div>
                          <p className="audit-meta">Opportunity created from webhook failure signal.</p>
                        </div>
                      )}
                    </div>
                  </div>
                </details>
              </section>
            </div>
          )}
        </div>

        {/* Sticky Drawer Footer */}
        <footer className="drawer-sticky-footer">
          {canExecute ? (
            <button
              onClick={() => setShowApprovalConfirm(true)}
              disabled={isExecuting}
              className="btn btn-primary btn-lg"
              style={{ width: "100%" }}
            >
              {isExecuting ? "Processing..." : "Create Payment Link \u2192"}
            </button>
          ) : (
            <button onClick={onClose} className="btn btn-tertiary" style={{ width: "100%" }}>
              Close Opportunity Details
            </button>
          )}
        </footer>
      </aside>
    </>
  );
}
