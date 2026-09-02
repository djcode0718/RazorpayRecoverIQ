import { useState, useRef, useEffect } from "react";
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
  activeTab?: string;
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
  activeTab,
}: HeaderProps) {
  const [showSimControls, setShowSimControls] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  // Close dropdown on outside click, Escape key, or scrolling
  useEffect(() => {
    if (!showSimControls) return;

    const handlePointerDown = (event: PointerEvent | MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowSimControls(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setShowSimControls(false);
        triggerRef.current?.focus();
      }
    };

    const handleScroll = () => {
      setShowSimControls(false);
    };

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    window.addEventListener("scroll", handleScroll, { passive: true, capture: true });

    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("scroll", handleScroll, { capture: true });
    };
  }, [showSimControls]);

  // Close dropdown whenever active tab changes
  useEffect(() => {
    setShowSimControls(false);
  }, [activeTab]);

  const handleSeedClick = () => {
    setShowSimControls(false);
    onSeedDemo();
  };

  const handleResetClick = () => {
    setShowSimControls(false);
    onResetDemo();
  };

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
          {/* Demo Tour: Hidden by default. Enabled only via VITE_ENABLE_DEMO_TOUR=true or ?demo_tour=true for dev/reference */}
          {(import.meta.env.VITE_ENABLE_DEMO_TOUR === "true" ||
            (typeof window !== "undefined" &&
              (window.location.search.includes("demo_tour=true") ||
                window.localStorage.getItem("enable_demo_tour") === "true"))) &&
            onOpenDemoTour && (
              <button
                onClick={onOpenDemoTour}
                className="btn btn-tour-highlight btn-sm"
                title="Open Guided Product Pitch Tour"
              >
                🎬 2-Min Demo Tour
              </button>
            )}

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
          <div className="sim-dropdown-wrapper" ref={dropdownRef}>
            <button
              ref={triggerRef}
              id="sim-dropdown-trigger"
              onClick={() => setShowSimControls((prev) => !prev)}
              className="btn btn-tertiary btn-sm"
              title="Demo & Simulation Actions"
              aria-haspopup="true"
              aria-expanded={showSimControls}
              aria-controls="sim-dropdown-menu"
            >
              ⚙ Simulation ▾
            </button>
            {showSimControls && (
              <div
                id="sim-dropdown-menu"
                role="menu"
                aria-labelledby="sim-dropdown-trigger"
                className="sim-dropdown-menu"
              >
                <button
                  role="menuitem"
                  onClick={handleSeedClick}
                  disabled={isDemoMutating || isLoading}
                  className="sim-menu-item"
                >
                  🌱 Seed Failure Scenarios
                </button>
                <button
                  role="menuitem"
                  onClick={handleResetClick}
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
