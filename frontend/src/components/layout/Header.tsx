import { useState } from "react";
import { OperatingStatus } from "../../types";
import { ThemeToggle } from "../common/ThemeToggle";

type HeaderProps = {
  operatingStatus: OperatingStatus;
  isLoading: boolean;
  isDemoMutating: boolean;
  demoMessage: string;
  autoRefresh: boolean;
  onRefresh: () => void;
  onSeedDemo: () => void;
  onResetDemo: () => void;
  onToggleAutoRefresh: (enabled: boolean) => void;
  onOpenDemoTour: () => void;
};

export function Header({
  operatingStatus,
  isLoading,
  isDemoMutating,
  demoMessage,
  autoRefresh,
  onRefresh,
  onSeedDemo,
  onResetDemo,
  onToggleAutoRefresh,
  onOpenDemoTour,
}: HeaderProps) {
  const [showSimControls, setShowSimControls] = useState(false);

  const isPaymentTest = operatingStatus.payment_environment === "RAZORPAY TEST";
  const isWebhookGood = operatingStatus.webhook === "VERIFIED" || operatingStatus.webhook === "CONFIGURED";
  const isPolicyGood = operatingStatus.policy_engine === "ACTIVE";

  return (
    <header className="hero-header-panel panel">
      <div className="hero-brand-block">
        <div className="brand-badge-row">
          <span className="brand-logo-text">RecoverIQ</span>
          <span className="brand-sub-badge">Revenue Recovery OS</span>
          <div className="compact-status-pills">
            <span className={`status-dot-pill ${isPaymentTest ? "good" : "info"}`} title="Payment Gateway Environment">
              <span className="pulse-dot" />
              {operatingStatus.payment_environment === "RAZORPAY TEST" ? "Razorpay Test" : operatingStatus.payment_environment}
            </span>
            <span className={`status-dot-pill ${isWebhookGood ? "good" : "warn"}`} title="Webhook Verification Status">
              HMAC {isWebhookGood ? "Verified" : "Waiting"}
            </span>
            <span className={`status-dot-pill ${isPolicyGood ? "good" : "bad"}`} title="Deterministic Safety Gate Policy">
              Policy {isPolicyGood ? "7/7 Active" : "Degraded"}
            </span>
          </div>
        </div>
        <h1 className="hero-main-title">Revenue Recovery Command Center</h1>
        <p className="hero-subtitle">
          Real-time payment failure diagnosis, deterministic safety policy gates, and automated Razorpay recovery.
        </p>
      </div>

      <div className="hero-controls-block">
        <div className="hero-actions-row">
          <button
            onClick={onOpenDemoTour}
            className="btn btn-tour-highlight btn-sm"
            title="Open Guided Product Pitch Tour"
          >
            🎬 2-Min Demo Tour
          </button>

          <button
            onClick={onRefresh}
            disabled={isLoading}
            className="btn btn-secondary btn-sm"
            aria-label="Refresh telemetry data"
          >
            {isLoading ? "Refreshing..." : "↻ Refresh"}
          </button>

          <label className="auto-refresh-toggle" title="Auto-refresh every 15 seconds">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => onToggleAutoRefresh(e.target.checked)}
            />
            <span>Auto 15s</span>
          </label>

          {/* Compact Simulation Menu */}
          <div className="sim-dropdown-wrapper">
            <button
              onClick={() => setShowSimControls(!showSimControls)}
              className="btn btn-tertiary btn-sm"
              title="Demo & Simulation Actions"
            >
              ⚙ Simulation ▾
            </button>
            {showSimControls && (
              <div className="sim-dropdown-menu">
                <button
                  onClick={() => {
                    onSeedDemo();
                    setShowSimControls(false);
                  }}
                  disabled={isDemoMutating || isLoading}
                  className="sim-menu-item"
                >
                  🌱 Seed Failure Scenarios
                </button>
                <button
                  onClick={() => {
                    onResetDemo();
                    setShowSimControls(false);
                  }}
                  disabled={isDemoMutating || isLoading}
                  className="sim-menu-item danger"
                >
                  ↺ Reset Simulation
                </button>
              </div>
            )}
          </div>

          <ThemeToggle />
        </div>
      </div>

      {demoMessage && (
        <div className="demo-message-banner">
          <span>{demoMessage}</span>
        </div>
      )}
    </header>
  );
}
