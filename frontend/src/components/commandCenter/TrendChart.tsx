import { useState } from "react";
import { TrendDataPoint } from "../../types";
import { formatMinorCurrency } from "../../utils/formatters";

type TrendChartProps = {
  data: TrendDataPoint[];
  error?: string | null;
  onRetry?: () => void;
};

export function TrendChart({ data, error, onRetry }: TrendChartProps) {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  if (error) {
    return (
      <div className="panel trend-panel compact-chart-panel">
        <div className="panel-header-with-badge">
          <h2>Revenue Recovery Performance</h2>
          <span className="badge badge-bad badge-sm">Error</span>
        </div>
        <div className="widget-error-box">
          <p>{error}</p>
          {onRetry && (
            <button onClick={onRetry} className="btn btn-tertiary btn-sm">
              Retry
            </button>
          )}
        </div>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="panel trend-panel compact-chart-panel">
        <div className="panel-header-with-badge">
          <h2>Revenue Recovery Performance</h2>
          <span className="badge badge-neutral badge-sm">Last 7 Days</span>
        </div>
        <div className="empty-state-mini">
          <p>No historical trend data available.</p>
        </div>
      </div>
    );
  }

  const maxVal =
    Math.max(
      ...data.map((d) => Math.max(d.revenue_at_risk_minor, d.recovered_revenue_minor)),
      100000
    ) * 1.15;

  const width = 600;
  const height = 230;
  const paddingLeft = 65;
  const paddingRight = 20;
  const paddingTop = 20;
  const paddingBottom = 32;

  const graphWidth = width - paddingLeft - paddingRight;
  const graphHeight = height - paddingTop - paddingBottom;
  const xSpacing = graphWidth / (data.length - 1 || 1);

  const getX = (index: number) => paddingLeft + index * xSpacing;
  const getY = (val: number) => paddingTop + graphHeight - (val / maxVal) * graphHeight;

  const riskPath = data
    .map((d, i) => `${i === 0 ? "M" : "L"}${getX(i)} ${getY(d.revenue_at_risk_minor)}`)
    .join(" ");

  const recoveredPath = data
    .map((d, i) => `${i === 0 ? "M" : "L"}${getX(i)} ${getY(d.recovered_revenue_minor)}`)
    .join(" ");

  // Area under recovered curve
  const recoveredAreaPath = `${recoveredPath} L${getX(data.length - 1)} ${paddingTop + graphHeight} L${getX(0)} ${paddingTop + graphHeight} Z`;

  const hoveredPoint = hoveredIdx !== null ? data[hoveredIdx] : null;

  return (
    <div className="panel trend-panel compact-chart-panel">
      <div className="panel-header-with-badge">
        <div>
          <h2>Revenue Recovery Performance</h2>
          <p className="panel-copy">Recovered revenue yield vs. failed transaction exposure.</p>
        </div>
        <div className="chart-legend">
          <div className="legend-item">
            <span className="legend-line line-risk" />
            <span>Exposure</span>
          </div>
          <div className="legend-item">
            <span className="legend-line line-recovered" />
            <strong className="text-good">Recovered</strong>
          </div>
        </div>
      </div>

      <div className="trend-chart-wrapper">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="svg-chart"
          aria-label="Revenue Recovery Trend Chart"
        >
          <defs>
            <linearGradient id="recoveredGradient" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="var(--good)" stopOpacity="0.25" />
              <stop offset="100%" stopColor="var(--good)" stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {/* Grid lines */}
          {[0, 0.33, 0.66, 1].map((ratio) => {
            const yVal = paddingTop + graphHeight * ratio;
            const labelVal = maxVal * (1 - ratio);
            return (
              <g key={ratio}>
                <line
                  x1={paddingLeft}
                  y1={yVal}
                  x2={width - paddingRight}
                  y2={yVal}
                  stroke="var(--line)"
                  strokeWidth="1"
                  strokeDasharray="4 4"
                />
                <text
                  x={paddingLeft - 8}
                  y={yVal + 4}
                  textAnchor="end"
                  fontSize="10"
                  fill="var(--text-muted)"
                  fontFamily="Inter, sans-serif"
                >
                  {formatMinorCurrency(Math.round(labelVal))}
                </text>
              </g>
            );
          })}

          {/* Area fill */}
          <path d={recoveredAreaPath} fill="url(#recoveredGradient)" />

          {/* Risk Exposure line (dashed) */}
          <path
            d={riskPath}
            fill="none"
            stroke="var(--line-strong)"
            strokeWidth="2"
            strokeDasharray="4 4"
          />

          {/* Recovered line (solid emerald) */}
          <path
            d={recoveredPath}
            fill="none"
            stroke="var(--good-text)"
            strokeWidth="2.5"
          />

          {/* X Axis labels */}
          {data.map((d, i) => (
            <text
              key={d.date}
              x={getX(i)}
              y={height - 8}
              textAnchor="middle"
              fontSize="10"
              fill="var(--text-muted)"
              fontFamily="Inter, sans-serif"
            >
              {d.display_date}
            </text>
          ))}

          {/* Interactive hover circles & columns */}
          {data.map((d, i) => {
            const isHovered = hoveredIdx === i;
            return (
              <g
                key={d.date}
                className="chart-hover-col"
                onMouseEnter={() => setHoveredIdx(i)}
                onMouseLeave={() => setHoveredIdx(null)}
                style={{ cursor: "pointer" }}
              >
                {/* Invisible hover hitbox */}
                <rect
                  x={getX(i) - xSpacing / 2}
                  y={paddingTop}
                  width={xSpacing}
                  height={graphHeight}
                  fill="transparent"
                />

                {isHovered && (
                  <line
                    x1={getX(i)}
                    y1={paddingTop}
                    x2={getX(i)}
                    y2={paddingTop + graphHeight}
                    stroke="var(--primary)"
                    strokeWidth="1"
                    strokeDasharray="2 2"
                  />
                )}

                <circle
                  cx={getX(i)}
                  cy={getY(d.recovered_revenue_minor)}
                  r={isHovered ? 6 : 4}
                  fill="var(--good-text)"
                  stroke="var(--panel)"
                  strokeWidth="2"
                />
              </g>
            );
          })}
        </svg>

        {/* Floating Tooltip */}
        {hoveredPoint && (
          <div className="chart-floating-tooltip">
            <strong>{hoveredPoint.display_date} ({hoveredPoint.date})</strong>
            <div className="tooltip-metrics">
              <span>Exposure: <strong>{formatMinorCurrency(hoveredPoint.revenue_at_risk_minor)}</strong></span>
              <span>Recovered: <strong className="text-good">{formatMinorCurrency(hoveredPoint.recovered_revenue_minor)}</strong></span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
