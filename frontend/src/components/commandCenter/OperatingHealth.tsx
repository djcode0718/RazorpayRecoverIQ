import { HealthItem } from "../../types";
import { toToneForOutcome } from "../../utils/formatters";
import { Badge } from "../common/Badge";

type OperatingHealthProps = {
  healthItems: HealthItem[];
};

export function OperatingHealth({ healthItems }: OperatingHealthProps) {
  return (
    <div className="panel health-panel compact-health-card">
      <div className="panel-header-with-badge">
        <div>
          <h2>Operating Gateway Health</h2>
          <p className="panel-copy">Connectivity, AI inference, and safety engine status.</p>
        </div>
        <span className="badge badge-good badge-sm">100% Operational</span>
      </div>

      <div className="health-grid-compact">
        {healthItems.map((item) => (
          <article key={item.label} className="health-item-compact">
            <div className="health-head">
              <span className="health-label">{item.label}</span>
              <Badge
                text={item.statusText || (item.healthy ? "HEALTHY" : "DEGRADED")}
                tone={toToneForOutcome(item.statusText || (item.healthy ? "PASS" : "FAIL"))}
                size="sm"
              />
            </div>
            <p className="health-note">{item.note}</p>
          </article>
        ))}
      </div>
    </div>
  );
}
