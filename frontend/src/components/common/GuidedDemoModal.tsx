import { useState } from "react";

type GuidedDemoModalProps = {
  isOpen: boolean;
  onClose: () => void;
  onNavigateTab: (tab: string) => void;
  onSelectTopOpportunity: () => void;
};

const DEMO_STEPS = [
  {
    step: 1,
    title: "1. Revenue at Risk & Executive Briefing",
    subtitle: "Quantify the problem within 10 seconds",
    description:
      "CFOs & revenue leaders immediately see ₹53,840.00 total exposure across 12 active opportunities. The 5-stage conversion funnel and 6 executive KPIs demonstrate exact recoverable capital potential.",
    targetTab: "Command Center",
    actionLabel: "View Command Center",
  },
  {
    step: 2,
    title: "2. Algorithmically Ranked Priority Queue",
    subtitle: "Decision support, not guesswork",
    description:
      "Opportunities are prioritized using transparent multi-factor scoring (Financial Impact × Recovery Confidence × Urgency × Policy Clearance). Executives immediately know which customer failure to address first.",
    targetTab: "Command Center",
    actionLabel: "Inspect Priority Queue",
  },
  {
    step: 3,
    title: "3. Auditable AI Diagnosis & 7/7 Policy Gates",
    subtitle: "Explainable ML, not a black box",
    description:
      "Open any opportunity to inspect the 8-stage lifecycle journey. AI diagnoses the exact root cause (e.g., transient network timeout) with 94% confidence, and the deterministic safety engine verifies 7/7 mandatory risk controls.",
    targetTab: "Opportunities",
    actionLabel: "Open Top Opportunity",
  },
  {
    step: 4,
    title: "4. Razorpay Money Loop Execution",
    subtitle: "Automated recovery action in 1-click",
    description:
      "Trigger automated recovery to dispatch a smart Razorpay payment link. Operators maintain human-in-the-loop oversight while automating repetitive invoice and subscription recovery.",
    targetTab: "Opportunities",
    actionLabel: "Test Razorpay Action",
  },
  {
    step: 5,
    title: "5. Statistical Model Evaluation & A/B Benchmark",
    subtitle: "Rigorous empirical proof of lift",
    description:
      "Switch to the Evaluation Center to inspect the holdout test benchmark. RecoverIQ outperforms naive retry baselines across F1 score, precision, recall, and captures +₹28,500 incremental yield while cutting false-positive penalty fees.",
    targetTab: "Evaluation",
    actionLabel: "Inspect Evaluation Matrix",
  },
  {
    step: 6,
    title: "6. Trust Center & Production Readiness Scorecard",
    subtitle: "Enterprise security & release gate confidence",
    description:
      "Verify cryptographic HMAC-SHA256 webhook signatures, zero-state duplicate idempotency, and the transparent 10-point Production Readiness Scorecard with telemetry evidence.",
    targetTab: "Production Readiness",
    actionLabel: "View Readiness Scorecard",
  },
];

export function GuidedDemoModal({
  isOpen,
  onClose,
  onNavigateTab,
  onSelectTopOpportunity,
}: GuidedDemoModalProps) {
  const [currentStepIndex, setCurrentStepIndex] = useState(0);

  if (!isOpen) return null;

  const currentStep = DEMO_STEPS[currentStepIndex];

  const handleStepAction = () => {
    if (currentStep.step === 3 || currentStep.step === 4) {
      onSelectTopOpportunity();
      onNavigateTab("Opportunities");
    } else {
      onNavigateTab(currentStep.targetTab);
    }
  };

  return (
    <div className="modal-backdrop open" onClick={onClose} role="dialog" aria-modal="true">
      <div className="modal-container demo-tour-modal" onClick={(e) => e.stopPropagation()}>
        <div className="demo-tour-header">
          <div className="demo-tour-title-group">
            <span className="demo-tour-pill">BUILDATHON 2-MINUTE PITCH</span>
            <h2>{currentStep.title}</h2>
            <p className="demo-tour-sub">{currentStep.subtitle}</p>
          </div>
          <button className="drawer-close-btn" onClick={onClose}>
            &times;
          </button>
        </div>

        <div className="demo-tour-body">
          <div className="demo-tour-stepper">
            {DEMO_STEPS.map((s, idx) => (
              <button
                key={s.step}
                className={`tour-step-dot ${idx === currentStepIndex ? "active" : idx < currentStepIndex ? "completed" : ""}`}
                onClick={() => setCurrentStepIndex(idx)}
                title={s.title}
              >
                {idx < currentStepIndex ? "✓" : s.step}
              </button>
            ))}
          </div>

          <div className="demo-step-description-box">
            <p>{currentStep.description}</p>
          </div>
        </div>

        <div className="demo-tour-footer">
          <button
            onClick={() => setCurrentStepIndex((prev) => Math.max(0, prev - 1))}
            disabled={currentStepIndex === 0}
            className="btn btn-tertiary btn-sm"
          >
            &larr; Previous Step
          </button>

          <div className="tour-footer-right">
            <button onClick={handleStepAction} className="btn btn-secondary btn-sm">
              {currentStep.actionLabel} &rarr;
            </button>

            {currentStepIndex < DEMO_STEPS.length - 1 ? (
              <button
                onClick={() => setCurrentStepIndex((prev) => prev + 1)}
                className="btn btn-primary btn-sm"
              >
                Next Pitch Step &rarr;
              </button>
            ) : (
              <button onClick={onClose} className="btn btn-primary btn-sm">
                Finish Pitch Tour ✓
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
