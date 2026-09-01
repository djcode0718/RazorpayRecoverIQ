import { Tone } from "../types";

export function formatMinorCurrency(
  minorUnits: number | null | undefined,
  options?: { exact?: boolean; decimals?: number }
): string {
  const value = typeof minorUnits === "number" && !Number.isNaN(minorUnits) ? minorUnits : 0;
  const isWhole = value % 100 === 0;
  const fractionDigits =
    options?.decimals !== undefined
      ? options.decimals
      : options?.exact
      ? 2
      : isWhole
      ? 0
      : 2;

  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value / 100);
}

export function formatIndianCount(num: number | null | undefined): string {
  const value = typeof num === "number" && !Number.isNaN(num) ? num : 0;
  return new Intl.NumberFormat("en-IN").format(value);
}

export function formatPercentage(value: number | null | undefined, isDecimalFraction = false): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "-";
  }
  let isDecimal = isDecimalFraction;
  if (value > 0 && value <= 1.0) {
    isDecimal = true;
  } else if (value > 1.0) {
    isDecimal = false;
  }
  const percentValue = isDecimal ? value * 100 : value;
  return `${percentValue.toFixed(1)}%`;
}

export function formatIsoTimestamp(input: string | null | undefined): string {
  if (!input) {
    return "-";
  }
  const value = new Date(input);
  if (Number.isNaN(value.getTime())) {
    return input;
  }
  return value.toLocaleString("en-IN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function formatTimeOnly(input: string | null | undefined): string {
  if (!input) {
    return "-";
  }
  const value = new Date(input);
  if (Number.isNaN(value.getTime())) {
    return input;
  }
  return value.toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function toTitle(value: string): string {
  return value
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\w\S*/g, (word) => `${word.charAt(0).toUpperCase()}${word.slice(1).toLowerCase()}`);
}

export function parseNumber(input: string, fallback: number): number {
  const parsed = Number.parseInt(input, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function toToneForOutcome(value: string | null | undefined): Tone {
  const normalized = (value || "").toUpperCase();
  if (["SUCCESS", "RECOVERED", "CAPTURED", "PASS", "ALLOW", "READY", "PROCESSED", "HEALTHY"].some((item) => normalized.includes(item))) {
    return "good";
  }
  if (["FAILED", "FAIL", "BLOCK", "CANCEL", "DISCONNECTED", "UNAVAILABLE", "IGNORED"].some((item) => normalized.includes(item))) {
    return "bad";
  }
  if (["WARN", "PARTIAL", "WAITING", "DEGRADED", "ESCALAT", "PENDING"].some((item) => normalized.includes(item))) {
    return "warn";
  }
  if (["INFO", "SIMULATION", "TEST", "AI RECOMMENDED", "LOCAL"].some((item) => normalized.includes(item))) {
    return "info";
  }
  return "neutral";
}

export function toToneForRisk(value: string | null | undefined): Tone {
  const normalized = (value || "").toUpperCase();
  if (normalized.includes("HIGH") || normalized.includes("CRITICAL")) {
    return "bad";
  }
  if (normalized.includes("MED")) {
    return "warn";
  }
  if (normalized.includes("LOW")) {
    return "good";
  }
  return "neutral";
}

export function isLikelyUrl(value: string | null | undefined): boolean {
  if (!value) return false;
  return /^https?:\/\//i.test(value);
}
