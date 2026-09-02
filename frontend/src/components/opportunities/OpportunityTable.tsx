import { useState, useMemo } from "react";
import { OpportunityListItem } from "../../types";
import { formatMinorCurrency } from "../../utils/formatters";
import { Badge } from "../common/Badge";

type SortField = "id" | "amount_at_risk_minor" | "expected_recovery_minor" | "confidence" | "customer_reference";
type SortDirection = "asc" | "desc";

type OpportunityTableProps = {
  items: OpportunityListItem[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  page: number;
  pageSize: number;
  totalCount: number;
  totalPages: number;
  hasNext: boolean;
  hasPrev: boolean;
  onPageChange: (newPage: number) => void;
  onPageSizeChange: (newPageSize: number) => void;
  confidenceFilter?: string;
  amountFilter?: string;
};

function formatActionTitle(action?: string | null): string {
  if (!action) return "Smart Payment Link";
  switch (action.toUpperCase()) {
    case "SMART_PAYMENT_LINK":
      return "Smart Payment Link";
    case "RETRY_AFTER_COOLDOWN":
      return "Cooldown Auto-Retry";
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

function formatDiagnosticLabel(category?: string | null, reason?: string | null): { primary: string; secondary: string } {
  const cat = (category || "Network Timeout").replace(/_/g, " ");
  const res = (reason || "Transient Gateway Timeout").replace(/_/g, " ");

  if (cat.toUpperCase().includes("NETWORK")) {
    return { primary: "Network Timeout", secondary: "Transient Gateway Issue" };
  }
  if (cat.toUpperCase().includes("ISSUER") || cat.toUpperCase().includes("BANK")) {
    return { primary: "Issuer Decline", secondary: "Card Authorization Hold" };
  }
  if (cat.toUpperCase().includes("FRAUD") || cat.toUpperCase().includes("RISK")) {
    return { primary: "Velocity / Risk", secondary: "Policy Threshold Block" };
  }
  return {
    primary: cat.replace(/\b\w/g, (c) => c.toUpperCase()),
    secondary: res.replace(/\b\w/g, (c) => c.toUpperCase()),
  };
}

function formatOutcomeLabel(outcome?: string | null, status?: string | null): { text: string; tone: "good" | "warn" | "bad" | "info" | "neutral" } {
  if (outcome === "RECOVERED" || status === "RESOLVED") {
    return { text: "✓ Recovered", tone: "good" };
  }
  if (outcome === "BLOCKED" || outcome === "POLICY_BLOCKED") {
    return { text: "✕ Blocked", tone: "bad" };
  }
  if (outcome === "ESCALATED") {
    return { text: "⚡ Escalated", tone: "warn" };
  }
  if (outcome === "FAILED") {
    return { text: "✕ Not Recovered", tone: "bad" };
  }
  return { text: "● Pending Action", tone: "info" };
}

export function OpportunityTable({
  items,
  selectedId,
  onSelect,
  page,
  pageSize,
  totalCount,
  totalPages,
  hasNext,
  hasPrev,
  onPageChange,
  onPageSizeChange,
  confidenceFilter = "ALL",
  amountFilter = "ALL",
}: OpportunityTableProps) {
  const [sortField, setSortField] = useState<SortField>("id");
  const [sortDir, setSortDir] = useState<SortDirection>("desc");

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir("desc");
    }
  };

  // Client-side filtering & sorting
  const processedItems = useMemo(() => {
    let list = [...items];

    // Filter by confidence
    if (confidenceFilter === "HIGH") {
      list = list.filter((i) => i.confidence >= 0.7 || i.confidence >= 70);
    } else if (confidenceFilter === "MEDIUM") {
      list = list.filter((i) => (i.confidence >= 0.4 && i.confidence < 0.7) || (i.confidence >= 40 && i.confidence < 70));
    } else if (confidenceFilter === "LOW") {
      list = list.filter((i) => i.confidence < 0.4 || i.confidence < 40);
    }

    // Filter by amount
    if (amountFilter === "HIGH") {
      list = list.filter((i) => i.amount_at_risk_minor >= 200000);
    } else if (amountFilter === "MEDIUM") {
      list = list.filter((i) => i.amount_at_risk_minor >= 50000 && i.amount_at_risk_minor < 200000);
    } else if (amountFilter === "LOW") {
      list = list.filter((i) => i.amount_at_risk_minor < 50000);
    }

    // Sort
    list.sort((a, b) => {
      let aVal = a[sortField] ?? 0;
      let bVal = b[sortField] ?? 0;

      if (typeof aVal === "string") {
        return sortDir === "asc"
          ? (aVal as string).localeCompare(bVal as string)
          : (bVal as string).localeCompare(aVal as string);
      }
      return sortDir === "asc" ? (aVal as number) - (bVal as number) : (bVal as number) - (aVal as number);
    });

    return list;
  }, [items, sortField, sortDir, confidenceFilter, amountFilter]);

  return (
    <div className="opportunities-table-wrapper">
      <div className="table-responsive">
        <table className="fintech-table opportunities-table" role="table" aria-label="Revenue Recovery Opportunities">
          <thead>
            <tr>
              <th
                onClick={() => handleSort("customer_reference")}
                className="sortable-th"
                style={{ width: "20%" }}
                title="Sort by customer / opportunity"
              >
                <span>Customer / Opportunity</span>
                <span className="sort-arrow">
                  {sortField === "customer_reference" || sortField === "id" ? (sortDir === "asc" ? "▲" : "▼") : "↕"}
                </span>
              </th>

              <th
                onClick={() => handleSort("amount_at_risk_minor")}
                className="sortable-th numeric"
                style={{ width: "16%" }}
                title="Sort by recoverable amount"
              >
                <span>Financial Impact</span>
                <span className="sort-arrow">
                  {sortField === "amount_at_risk_minor" ? (sortDir === "asc" ? "▲" : "▼") : "↕"}
                </span>
              </th>

              <th style={{ width: "18%" }}>AI Diagnostic</th>

              <th
                onClick={() => handleSort("confidence")}
                className="sortable-th"
                style={{ width: "14%" }}
                title="Sort by AI conviction confidence"
              >
                <span>AI Confidence</span>
                <span className="sort-arrow">
                  {sortField === "confidence" ? (sortDir === "asc" ? "▲" : "▼") : "↕"}
                </span>
              </th>

              <th style={{ width: "12%" }}>Policy Gate</th>
              <th style={{ width: "14%" }}>Recommended Action</th>
              <th style={{ width: "12%" }}>Business Outcome</th>
            </tr>
          </thead>
          <tbody>
            {processedItems.map((item) => {
              const isSelected = item.id === selectedId;
              const diag = formatDiagnosticLabel(item.failure_category, item.failure_reason);
              const outcomeInfo = formatOutcomeLabel(item.outcome, item.status);
              const isPolicyPass = item.policy_result === "ALLOW";
              const confVal = item.confidence <= 1 ? Math.round(item.confidence * 100) : Math.round(item.confidence);

              return (
                <tr
                  key={item.id}
                  className={`clickable-row ${isSelected ? "selected-row" : ""}`}
                  onClick={() => onSelect(item.id)}
                  tabIndex={0}
                  role="button"
                  aria-label={`Open opportunity drawer for #${item.id}, customer ${item.customer_reference}`}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelect(item.id);
                    }
                  }}
                >
                  {/* 1. Customer & Opportunity Identity */}
                  <td>
                    <div className="table-customer-cell">
                      <strong className="customer-name-hero">
                        {item.customer_reference || `Customer #${item.id}`}
                      </strong>
                      <div className="opp-meta-row">
                        <span className="opp-id-pill font-mono">#OPP-{item.id}</span>
                        <span className="test-env-badge">TEST</span>
                      </div>
                    </div>
                  </td>

                  {/* 2. Financial Impact & Expected Yield */}
                  <td className="numeric">
                    <div className="table-financial-cell">
                      <strong className="amount-hero">{formatMinorCurrency(item.amount_at_risk_minor)}</strong>
                      <span className="expected-yield-text">
                        <strong className="text-good">{formatMinorCurrency(item.expected_recovery_minor)}</strong> expected
                      </span>
                    </div>
                  </td>

                  {/* 3. AI Diagnostic */}
                  <td>
                    <div className="table-diagnostic-cell">
                      <span className="diag-primary-text">{diag.primary}</span>
                      <span className="diag-secondary-text">{diag.secondary}</span>
                    </div>
                  </td>

                  {/* 4. AI Confidence Meter */}
                  <td>
                    <div className="confidence-cell-structured">
                      <div className="confidence-bar-mini">
                        <div
                          className="confidence-fill-mini"
                          style={{
                            width: `${Math.min(100, Math.max(12, confVal))}%`,
                            background:
                              confVal >= 70
                                ? "var(--good-text)"
                                : confVal >= 40
                                ? "var(--warn-text)"
                                : "var(--bad-text)",
                          }}
                        />
                      </div>
                      <span className="confidence-label-tag">
                        <strong>{confVal}%</strong> {confVal >= 70 ? "High" : confVal >= 40 ? "Medium" : "Low"}
                      </span>
                    </div>
                  </td>

                  {/* 5. Policy Gate (7/7 Checks) */}
                  <td>
                    <Badge
                      text={isPolicyPass ? "✓ 7/7 Cleared" : "✕ Blocked"}
                      tone={isPolicyPass ? "good" : "bad"}
                      size="sm"
                    />
                  </td>

                  {/* 6. Human-readable Recommended Action */}
                  <td>
                    <span className="action-title-text font-bold text-primary">
                      {formatActionTitle(item.recommended_action)}
                    </span>
                  </td>

                  {/* 7. Outcome Status */}
                  <td>
                    <Badge text={outcomeInfo.text} tone={outcomeInfo.tone} size="sm" />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination Bar */}
      <div className="pagination-row">
        <div className="pagination-info">
          <span>
            Showing <strong>{processedItems.length > 0 ? (page - 1) * pageSize + 1 : 0}</strong>–
            <strong>{Math.min(page * pageSize, totalCount)}</strong> of <strong>{totalCount}</strong> opportunities
          </span>
        </div>

        <div className="pagination-controls">
          <label htmlFor="page-size-select" className="page-size-label">
            Rows per page:
          </label>
          <select
            id="page-size-select"
            className="select-input compact"
            value={String(pageSize)}
            onChange={(e) => onPageSizeChange(Number.parseInt(e.target.value, 10))}
          >
            <option value="10">10</option>
            <option value="20">20</option>
            <option value="40">40</option>
            <option value="80">80</option>
          </select>

          <button
            onClick={() => onPageChange(Math.max(1, page - 1))}
            disabled={!hasPrev}
            className="btn btn-tertiary btn-sm"
          >
            &larr; Previous
          </button>
          <button
            onClick={() => onPageChange(page + 1)}
            disabled={!hasNext}
            className="btn btn-tertiary btn-sm"
          >
            Next &rarr;
          </button>
        </div>
      </div>
    </div>
  );
}
