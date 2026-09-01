import { DashboardEvent } from "../../types";
import { formatTimeOnly } from "../../utils/formatters";
import { Badge } from "../common/Badge";

type EventStreamProps = {
  events: DashboardEvent[];
  error?: string | null;
  onRetry?: () => void;
};

export function EventStream({ events, error, onRetry }: EventStreamProps) {
  return (
    <div className="panel events-panel compact-events-card">
      <div className="panel-header-with-badge">
        <div>
          <h2>System Audit Event Stream</h2>
          <p className="panel-copy">Real-time cryptographic webhook & recovery dispatch log.</p>
        </div>
        <Badge text="Live Ledger" tone="info" size="sm" />
      </div>

      <div className="event-list-container">
        {error ? (
          <div className="widget-error-box">
            <p>{error}</p>
            {onRetry && (
              <button onClick={onRetry} className="btn btn-tertiary btn-sm">
                Retry
              </button>
            )}
          </div>
        ) : events.length === 0 ? (
          <div className="empty-state-mini">
            <p>Waiting for system recovery events...</p>
          </div>
        ) : (
          <div className="event-stream-compact-list">
            {events.slice(0, 5).map((evt) => (
              <div key={evt.id} className="compact-event-item">
                <span className="compact-event-dot" />
                <div className="compact-event-content">
                  <div className="compact-event-head">
                    <span className="compact-event-type font-mono">{evt.event_type}</span>
                    <span className="compact-event-time">{formatTimeOnly(evt.created_at)}</span>
                  </div>
                  <p className="compact-event-desc">
                    <strong>{evt.entity_type} {evt.entity_id}</strong>
                    {evt.result && <span className="event-result-tag text-good font-bold"> &bull; {evt.result}</span>}
                    {evt.reason && <span className="event-reason-tag text-soft"> &bull; {evt.reason}</span>}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
