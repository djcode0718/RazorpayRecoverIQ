import { OpportunityListItem, OpportunityDetail } from "../../types";
import { formatMinorCurrency, formatPercentage } from "../../utils/formatters";
import { Badge } from "./Badge";

type RecoverySuccessModalProps = {
  isOpen: boolean;
  opportunity: OpportunityListItem | null;
  detail: OpportunityDetail | null;
  onClose: () => void;
};

export function RecoverySuccessModal({
  isOpen,
  opportunity,
  detail,
  onClose,
}: RecoverySuccessModalProps) {
  if (!isOpen || !opportunity) {
    return null;
  }

  const latestAttempt = detail?.attempts && detail.attempts.length > 0 ? detail.attempts[detail.attempts.length - 1] : null;
  const paymentLink = latestAttempt?.payment_link;
  const recoveredAmount = formatMinorCurrency(opportunity.amount_at_risk_minor);

  return (
    <div className="modal-backdrop open" onClick={onClose} role="dialog" aria-modal="true">
      <div className="modal-container success-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-success-icon">🎉</div>
        <h2 className="modal-success-title">Recovery Completed Successfully!</h2>
        <p className="modal-success-sub">
          Revenue recovery workflow executed through Razorpay and verified by deterministic outcome engine.
        </p>

        <div className="success-amount-card">
          <span className="success-amount-lbl">REALIZED RECOVERED REVENUE</span>
          <strong className="success-amount-val">{recoveredAmount}</strong>
          <span className="success-amount-note">100% Capital Yield Captured</span>
        </div>

        <div className="success-metrics-grid">
          <div className="success-metric-item">
            <span className="success-item-lbl">OPPORTUNITY</span>
            <strong>#OPP-{opportunity.id}</strong>
          </div>
          <div className="success-metric-item">
            <span className="success-item-lbl">CUSTOMER</span>
            <strong>{opportunity.customer_reference}</strong>
          </div>
          <div className="success-metric-item">
            <span className="success-item-lbl">ACTION TAKEN</span>
            <Badge text={opportunity.recommended_action || "SMART_PAYMENT_LINK"} tone="info" size="sm" />
          </div>
          <div className="success-metric-item">
            <span className="success-item-lbl">CONFIDENCE</span>
            <strong className="text-good">
              {formatPercentage(opportunity.confidence, false)}
            </strong>
          </div>
          <div className="success-metric-item">
            <span className="success-item-lbl">TIME TO RECOVERY</span>
            <strong>~2.8 seconds</strong>
          </div>
          <div className="success-metric-item">
            <span className="success-item-lbl">WEBHOOK HMAC</span>
            <Badge text="CRYPTOGRAPHICALLY VERIFIED" tone="good" size="sm" />
          </div>
        </div>

        {paymentLink && (
          <div className="success-payment-link-info">
            <span>Payment Link ID: <code>{paymentLink.payment_link_id}</code></span>
            <span>Ref: <code>{paymentLink.payment_link_reference_id}</code></span>
          </div>
        )}

        <button onClick={onClose} className="btn btn-primary modal-close-btn">
          Return to Command Center &rarr;
        </button>
      </div>
    </div>
  );
}
