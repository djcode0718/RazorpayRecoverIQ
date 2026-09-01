import React from "react";
import { Badge } from "./Badge";
import { Tone } from "../../types";

type KpiCardProps = {
  title: string;
  value: string;
  subtext?: string;
  badge?: {
    text: string;
    tone: Tone;
  };
  highlightTone?: "good" | "info" | "warn" | "bad";
  isHero?: boolean;
  onClick?: () => void;
  tooltip?: string;
};

export function KpiCard({
  title,
  value,
  subtext,
  badge,
  highlightTone,
  isHero = false,
  onClick,
  tooltip,
}: KpiCardProps) {
  const isClickable = Boolean(onClick);

  return (
    <article
      className={`kpi-metric-card ${isHero ? "hero-kpi" : ""} ${isClickable ? "clickable-kpi" : ""}`}
      onClick={onClick}
      title={tooltip}
      role={isClickable ? "button" : undefined}
      tabIndex={isClickable ? 0 : undefined}
      onKeyDown={(e) => {
        if (isClickable && onClick && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          onClick();
        }
      }}
    >
      <div className="kpi-card-head">
        <span className="kpi-label">{title}</span>
        {badge && <Badge text={badge.text} tone={badge.tone} size="sm" />}
      </div>
      <span className={`kpi-value ${highlightTone || ""}`}>{value}</span>
      {subtext && <p className="kpi-subtext">{subtext}</p>}
      {isClickable && <span className="kpi-click-hint">Click to inspect &rarr;</span>}
    </article>
  );
}
