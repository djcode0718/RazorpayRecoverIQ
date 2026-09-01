export function TableSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="table-responsive">
      <table className="fintech-table skeleton-table" aria-hidden="true">
        <thead>
          <tr>
            <th>Opportunity</th>
            <th>Revenue at Risk</th>
            <th>Failure Reason</th>
            <th>Recovery Confidence</th>
            <th>Policy Gate</th>
            <th>Recommended Action</th>
            <th>Outcome</th>
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }).map((_, idx) => (
            <tr key={idx}>
              <td>
                <div className="skeleton skeleton-text" style={{ width: "80px", height: "16px" }} />
                <div className="skeleton skeleton-text" style={{ width: "110px", height: "12px", marginTop: "4px" }} />
              </td>
              <td>
                <div className="skeleton skeleton-text" style={{ width: "90px", height: "16px" }} />
                <div className="skeleton skeleton-text" style={{ width: "70px", height: "12px", marginTop: "4px" }} />
              </td>
              <td>
                <div className="skeleton skeleton-text" style={{ width: "100px", height: "16px" }} />
                <div className="skeleton skeleton-text" style={{ width: "80px", height: "12px", marginTop: "4px" }} />
              </td>
              <td>
                <div className="skeleton skeleton-badge" style={{ width: "65px", height: "20px" }} />
              </td>
              <td>
                <div className="skeleton skeleton-badge" style={{ width: "75px", height: "20px" }} />
              </td>
              <td>
                <div className="skeleton skeleton-text" style={{ width: "100px", height: "16px" }} />
              </td>
              <td>
                <div className="skeleton skeleton-badge" style={{ width: "85px", height: "20px" }} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function DrawerSkeleton() {
  return (
    <div className="detail-layout skeleton-layout" style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
      <div className="panel" style={{ padding: "16px" }}>
        <div className="skeleton" style={{ width: "140px", height: "16px", marginBottom: "12px" }} />
        <div style={{ display: "flex", gap: "8px" }}>
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="skeleton" style={{ flex: 1, height: "32px", borderRadius: "6px" }} />
          ))}
        </div>
      </div>

      <div className="panel" style={{ padding: "16px" }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "12px" }}>
          <div className="skeleton" style={{ height: "48px", borderRadius: "6px" }} />
          <div className="skeleton" style={{ height: "48px", borderRadius: "6px" }} />
          <div className="skeleton" style={{ height: "48px", borderRadius: "6px" }} />
        </div>
      </div>

      <div className="panel" style={{ padding: "16px" }}>
        <div className="skeleton" style={{ width: "180px", height: "18px", marginBottom: "12px" }} />
        <div className="skeleton" style={{ width: "90%", height: "14px", marginBottom: "8px" }} />
        <div className="skeleton" style={{ width: "70%", height: "14px" }} />
      </div>

      <div className="panel" style={{ padding: "16px" }}>
        <div className="skeleton" style={{ width: "160px", height: "18px", marginBottom: "12px" }} />
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="skeleton" style={{ height: "24px", borderRadius: "4px" }} />
          ))}
        </div>
      </div>
    </div>
  );
}

export function KpiGridSkeleton() {
  return (
    <div className="kpi-hierarchy-grid">
      {Array.from({ length: 6 }).map((_, idx) => (
        <div key={idx} className="kpi-metric-card skeleton-card">
          <div className="skeleton skeleton-text" style={{ width: "100px", height: "12px", marginBottom: "12px" }} />
          <div className="skeleton skeleton-text" style={{ width: "140px", height: "28px", marginBottom: "8px" }} />
          <div className="skeleton skeleton-text" style={{ width: "80px", height: "12px" }} />
        </div>
      ))}
    </div>
  );
}
