import { useState } from "react";
import { ReadinessCheck } from "../../types";
import { Badge } from "../common/Badge";

type ReadinessCheckGridProps = {
  checks: ReadinessCheck[];
};

type CheckMeta = {
  title: string;
  category: "Functionality" | "Reliability & Failover" | "Security" | "Observability & Audit" | "Data Integrity" | "Recovery Safety";
  description: string;
};

const CHECK_DEFINITIONS: Record<string, CheckMeta> = {
  db_connectivity: {
    title: "Database Connectivity & Integrity",
    category: "Functionality",
    description: "Validates active connection, table schemas, and write throughput.",
  },
  opportunity_pipeline: {
    title: "Opportunity Ingestion Pipeline",
    category: "Functionality",
    description: "Verifies failed payment capture, customer reference mapping, and amount calculations.",
  },
  ai_fallback: {
    title: "AI Fallback & Timeout Resilience",
    category: "Reliability & Failover",
    description: "Ensures deterministic rule fallback activates seamlessly during AI provider outage.",
  },
  webhook_security: {
    title: "Webhook HMAC Signature Security",
    category: "Security",
    description: "Verifies HMAC-SHA256 signature verification rejects forged payloads with HTTP 401.",
  },
  security_redaction_guard: {
    title: "Error Sanitization & Redaction",
    category: "Security",
    description: "Ensures raw credentials, customer PII, and stack traces are redacted from responses.",
  },
  audit_logging: {
    title: "Cryptographic Audit Ledger",
    category: "Observability & Audit",
    description: "Verifies end-to-end timeline tracing for all diagnoses, policy gates, and webhooks.",
  },
  evaluation_data: {
    title: "Evaluation History Records",
    category: "Observability & Audit",
    description: "Ensures model performance benchmark records are persisted and queryable.",
  },
  reproducibility_probe: {
    title: "Dataset & Metric Reproducibility",
    category: "Data Integrity",
    description: "Validates deterministic random seeds generate identical F1 and recovery rate scores.",
  },
  policy_enforcement: {
    title: "Deterministic Policy Safety Gates",
    category: "Recovery Safety",
    description: "Validates 7/7 mandatory safety checks prevent unauthorized payment link dispatch.",
  },
  idempotency: {
    title: "Duplicate Webhook Idempotency",
    category: "Recovery Safety",
    description: "Guarantees repeated webhook deliveries with identical event IDs are safely ignored.",
  },
};

const CATEGORIES: Array<CheckMeta["category"]> = [
  "Functionality",
  "Reliability & Failover",
  "Security",
  "Observability & Audit",
  "Data Integrity",
  "Recovery Safety",
];

export function ReadinessCheckGrid({ checks }: ReadinessCheckGridProps) {
  const [selectedCategory, setSelectedCategory] = useState<string>("ALL");

  // Calculate actual category gate compliance
  const categoryStats = CATEGORIES.map((cat) => {
    const catChecks = checks.filter(
      (c) => (CHECK_DEFINITIONS[c.id]?.category || "Functionality") === cat
    );
    const passed = catChecks.filter((c) => c.status === "PASS").length;
    const total = catChecks.length || 1;
    const scorePct = Math.round((passed / total) * 100);

    return {
      category: cat,
      passed,
      total,
      scorePct,
      status: passed === total ? "PASS" : passed > 0 ? "PARTIAL" : "FAIL",
      summary: catChecks[0]?.message || "Subsystem requirements verified.",
      hasGap: passed < total,
    };
  });

  const filteredChecks = selectedCategory === "ALL"
    ? checks
    : checks.filter((c) => (CHECK_DEFINITIONS[c.id]?.category || "Functionality") === selectedCategory);

  const failingChecks = checks.filter((c) => c.status !== "PASS");

  return (
    <div className="readiness-breakdown-section">
      {/* 6 Category Dimension Cards */}
      <div className="readiness-category-cards-grid">
        {categoryStats.map((stat) => (
          <div
            key={stat.category}
            className={`readiness-category-card panel ${selectedCategory === stat.category ? "active" : ""}`}
            onClick={() => setSelectedCategory(selectedCategory === stat.category ? "ALL" : stat.category)}
            tabIndex={0}
            role="button"
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                setSelectedCategory(selectedCategory === stat.category ? "ALL" : stat.category);
              }
            }}
          >
            <div className="cat-card-header">
              <span className="cat-card-name">{stat.category}</span>
              <Badge
                text={stat.status}
                tone={stat.status === "PASS" ? "good" : stat.status === "PARTIAL" ? "warn" : "bad"}
                size="sm"
              />
            </div>
            <strong className="cat-card-score">{stat.scorePct}%</strong>
            <span className="cat-card-gates">
              {stat.passed} of {stat.total} gates passed
            </span>
            <p className="cat-card-desc">{stat.summary}</p>
          </div>
        ))}
      </div>

      {/* Release Blockers / Gaps Banner */}
      {failingChecks.length > 0 && (
        <div className="release-blockers-banner panel">
          <div className="blockers-header">
            <span className="blockers-icon">⚠️</span>
            <div>
              <strong>{failingChecks.length} Release Action Item{failingChecks.length > 1 ? "s" : ""} Required</strong>
              <p className="blockers-sub">The following items require remediation before general production sign-off:</p>
            </div>
          </div>
          <ul className="blockers-list">
            {failingChecks.map((chk) => {
              const meta = CHECK_DEFINITIONS[chk.id] || { title: chk.id };
              return (
                <li key={chk.id}>
                  <Badge text={chk.status} tone={chk.status === "FAIL" ? "bad" : "warn"} size="sm" />
                  <strong>{meta.title}:</strong>
                  <span>{chk.message}</span>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* Detailed Checks Grid with Clean Hierarchy & Progressive Disclosure */}
      <div className="panel readiness-checks-panel">
        <div className="panel-header-with-action">
          <div>
            <span className="section-step-tag">INDIVIDUAL RELEASE GATES</span>
            <h3>Production Gate Verification Checklist</h3>
          </div>
          {selectedCategory !== "ALL" && (
            <button onClick={() => setSelectedCategory("ALL")} className="btn btn-tertiary btn-sm">
              Show All Gates ({checks.length})
            </button>
          )}
        </div>
        <p className="panel-copy">
          Audited verification criteria across functional reliability, webhook signature validation, idempotency ledgers, and error redactions.
        </p>

        <div className="readiness-gates-grid">
          {filteredChecks.map((check) => {
            const meta = CHECK_DEFINITIONS[check.id] || {
              title: check.id,
              category: "Functionality",
              description: "System verification criteria.",
            };

            const isPass = check.status === "PASS";
            const isFail = check.status === "FAIL";

            return (
              <div key={check.id} className={`readiness-gate-item panel ${check.status.toLowerCase()}`}>
                <div className="gate-item-header">
                  <div className="gate-title-group">
                    <span className="gate-category-pill">{meta.category}</span>
                    <strong className="gate-title">{meta.title}</strong>
                  </div>
                  <Badge
                    text={check.status}
                    tone={isPass ? "good" : isFail ? "bad" : "warn"}
                    size="sm"
                  />
                </div>

                <p className="gate-desc">{meta.description}</p>

                <div className="gate-result-box">
                  <span className="gate-result-lbl">VERDICT MESSAGE:</span>
                  <p className="gate-message">{check.message}</p>
                </div>

                {check.evidence && Object.keys(check.evidence).length > 0 && (
                  <details className="technical-details-accordion">
                    <summary>
                      <span>📜 View Telemetry Evidence</span>
                      <span className="details-arrow">▾</span>
                    </summary>
                    <div className="details-content-box">
                      <pre className="raw-json-block font-mono">
                        {JSON.stringify(check.evidence, null, 2)}
                      </pre>
                    </div>
                  </details>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
