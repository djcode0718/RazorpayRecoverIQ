import { Tone } from "../../types";

type BadgeProps = {
  text: string;
  tone?: Tone;
  className?: string;
  size?: "sm" | "md";
  dot?: boolean;
};

export function Badge({ text, tone = "neutral", className = "", size = "md", dot = false }: BadgeProps) {
  return (
    <span className={`badge badge-${tone} badge-${size} ${className}`}>
      {dot && <span className="badge-dot" />}
      {text}
    </span>
  );
}
