import React, { useState, useEffect } from "react";

type OpportunityFiltersProps = {
  status: string;
  action: string;
  search: string;
  confidenceFilter?: string;
  amountFilter?: string;
  onFilterChange: (filters: {
    status: string;
    action: string;
    search: string;
    confidenceFilter?: string;
    amountFilter?: string;
  }) => void;
  onReset: () => void;
};

export function OpportunityFilters({
  status,
  action,
  search,
  confidenceFilter = "ALL",
  amountFilter = "ALL",
  onFilterChange,
  onReset,
}: OpportunityFiltersProps) {
  const [localSearch, setLocalSearch] = useState(search);
  const [localConfidence, setLocalConfidence] = useState(confidenceFilter);
  const [localAmount, setLocalAmount] = useState(amountFilter);

  useEffect(() => {
    setLocalSearch(search);
  }, [search]);

  useEffect(() => {
    setLocalConfidence(confidenceFilter);
  }, [confidenceFilter]);

  useEffect(() => {
    setLocalAmount(amountFilter);
  }, [amountFilter]);

  // Debounced search
  useEffect(() => {
    const timer = setTimeout(() => {
      if (localSearch !== search) {
        onFilterChange({
          status,
          action,
          search: localSearch,
          confidenceFilter: localConfidence,
          amountFilter: localAmount,
        });
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [localSearch, search, status, action, localConfidence, localAmount, onFilterChange]);

  const activeFilterCount = [
    status !== "ALL" ? 1 : 0,
    action !== "ALL" ? 1 : 0,
    localSearch.trim() !== "" ? 1 : 0,
    localConfidence !== "ALL" ? 1 : 0,
    localAmount !== "ALL" ? 1 : 0,
  ].reduce((a, b) => a + b, 0);

  return (
    <div className="filter-grid-enterprise panel">
      {/* 1. Search Box with Icon and Clear */}
      <div className="field-block search-field-enterprise">
        <label htmlFor="search-input">Search Opportunities</label>
        <div className="search-input-wrapper">
          <span className="search-icon-inside">🔍</span>
          <input
            id="search-input"
            className="text-input search-input-styled"
            value={localSearch}
            onChange={(e) => setLocalSearch(e.target.value)}
            placeholder="Search customer name, #OPP ID, failure archetype, action..."
          />
          {localSearch && (
            <button
              className="search-clear-btn"
              onClick={() => {
                setLocalSearch("");
                onFilterChange({
                  status,
                  action,
                  search: "",
                  confidenceFilter: localConfidence,
                  amountFilter: localAmount,
                });
              }}
              title="Clear search"
              aria-label="Clear search"
            >
              &times;
            </button>
          )}
        </div>
      </div>

      {/* 2. Lifecycle Status */}
      <div className="field-block">
        <label htmlFor="status-filter">Lifecycle Status</label>
        <select
          id="status-filter"
          className="select-input"
          value={status}
          onChange={(e) =>
            onFilterChange({
              status: e.target.value,
              action,
              search: localSearch,
              confidenceFilter: localConfidence,
              amountFilter: localAmount,
            })
          }
        >
          <option value="ALL">All Statuses</option>
          <option value="OPEN">Open (Action Required)</option>
          <option value="RESOLVED">Resolved (Settled Recovery)</option>
          <option value="CLOSED">Closed (Archived)</option>
        </select>
      </div>

      {/* 3. Recommended Action */}
      <div className="field-block">
        <label htmlFor="action-filter">Recovery Action</label>
        <select
          id="action-filter"
          className="select-input"
          value={action}
          onChange={(e) =>
            onFilterChange({
              status,
              action: e.target.value,
              search: localSearch,
              confidenceFilter: localConfidence,
              amountFilter: localAmount,
            })
          }
        >
          <option value="ALL">All Actions</option>
          <option value="SMART_PAYMENT_LINK">Smart Payment Link</option>
          <option value="RETRY_AFTER_COOLDOWN">Scheduled Cooldown Retry</option>
          <option value="RETRY">Immediate Gateway Retry</option>
          <option value="ESCALATE_TO_MANUAL">Manual Finance Review</option>
          <option value="BLOCK_AND_FLAG">Safety Policy Block</option>
        </select>
      </div>

      {/* 4. Confidence Bucket */}
      <div className="field-block">
        <label htmlFor="confidence-filter">AI Confidence</label>
        <select
          id="confidence-filter"
          className="select-input"
          value={localConfidence}
          onChange={(e) => {
            setLocalConfidence(e.target.value);
            onFilterChange({
              status,
              action,
              search: localSearch,
              confidenceFilter: e.target.value,
              amountFilter: localAmount,
            });
          }}
        >
          <option value="ALL">Any Confidence</option>
          <option value="HIGH">High (≥70%)</option>
          <option value="MEDIUM">Medium (40% - 69%)</option>
          <option value="LOW">Low (&lt;40%)</option>
        </select>
      </div>

      {/* 5. Amount Bucket */}
      <div className="field-block">
        <label htmlFor="amount-filter">Exposure Range</label>
        <select
          id="amount-filter"
          className="select-input"
          value={localAmount}
          onChange={(e) => {
            setLocalAmount(e.target.value);
            onFilterChange({
              status,
              action,
              search: localSearch,
              confidenceFilter: localConfidence,
              amountFilter: e.target.value,
            });
          }}
        >
          <option value="ALL">Any Amount</option>
          <option value="HIGH">High (&gt;₹2,000)</option>
          <option value="MEDIUM">Medium (₹500 - ₹2,000)</option>
          <option value="LOW">Low (&lt;₹500)</option>
        </select>
      </div>

      {/* 6. Filter Actions */}
      <div className="filter-actions-enterprise">
        {activeFilterCount > 0 && (
          <span className="active-filters-badge">
            {activeFilterCount} active filter{activeFilterCount > 1 ? "s" : ""}
          </span>
        )}
        <button
          onClick={() => {
            setLocalSearch("");
            setLocalConfidence("ALL");
            setLocalAmount("ALL");
            onReset();
          }}
          className="btn btn-tertiary btn-sm"
          title="Reset all filters"
        >
          Reset Filters
        </button>
      </div>
    </div>
  );
}
