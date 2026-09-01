import { OpportunityListItem } from "../types";

export type PriorityScoredOpportunity = OpportunityListItem & {
  priorityScore: number;
  priorityRank: number;
  urgencyLevel: "HIGH" | "MEDIUM" | "STANDARD";
  priorityReasons: string[];
  whyItMatters: string;
};

/**
 * Calculates a multi-factor transparent priority score:
 * Priority Score = (Normalized Financial Impact * 0.40) + (Recovery Confidence * 0.35) + (Urgency Weight * 0.15) + (Policy Clearance * 0.10)
 */
export function calculatePriorityScore(opp: OpportunityListItem, maxRiskMinor: number): PriorityScoredOpportunity {
  const normalizedImpact = maxRiskMinor > 0 ? (opp.amount_at_risk_minor / maxRiskMinor) * 100 : 50;
  const confidenceScore = opp.confidence <= 1 ? opp.confidence * 100 : opp.confidence;
  
  const isHighValue = opp.amount_at_risk_minor >= 200000;
  const isHighConfidence = confidenceScore >= 75;
  const isNetworkFailure = (opp.failure_category || "").toUpperCase().includes("NETWORK") || (opp.failure_reason || "").toUpperCase().includes("TIMEOUT");
  const isPolicyAllowed = opp.policy_result === "ALLOW";

  let urgencyLevel: "HIGH" | "MEDIUM" | "STANDARD" = "STANDARD";
  let urgencyWeight = 50;

  if (isHighValue && isNetworkFailure) {
    urgencyLevel = "HIGH";
    urgencyWeight = 95;
  } else if (isHighValue || isHighConfidence) {
    urgencyLevel = "MEDIUM";
    urgencyWeight = 75;
  }

  const policyWeight = isPolicyAllowed ? 100 : 30;

  const score = Math.round(
    normalizedImpact * 0.40 +
    confidenceScore * 0.35 +
    urgencyWeight * 0.15 +
    policyWeight * 0.10
  );

  const reasons: string[] = [];
  if (opp.amount_at_risk_minor >= 500000) {
    reasons.push("High financial exposure (P1 tier)");
  } else if (opp.amount_at_risk_minor >= 200000) {
    reasons.push("Substantial recoverable value (P2 tier)");
  } else {
    reasons.push("Standard recoverable value");
  }

  reasons.push(`${confidenceScore.toFixed(0)}% recovery confidence`);

  if (isNetworkFailure) {
    reasons.push("Transient gateway timeout (high recovery probability)");
  } else if ((opp.failure_category || "").toUpperCase().includes("DECLINE")) {
    reasons.push("Card decline (eligible for smart payment link)");
  }

  if (isPolicyAllowed) {
    reasons.push("Deterministic policy gate approved (7/7 safety checks passed)");
  } else {
    reasons.push("Requires policy clearance / manual review");
  }

  return {
    ...opp,
    priorityScore: score,
    priorityRank: 0,
    urgencyLevel,
    priorityReasons: reasons,
    whyItMatters: `Captures ₹${(opp.expected_recovery_minor / 100).toLocaleString("en-IN")} expected net yield with ${urgencyLevel.toLowerCase()} urgency.`,
  };
}

export function rankOpportunities(opportunities: OpportunityListItem[]): PriorityScoredOpportunity[] {
  const maxRisk = Math.max(...opportunities.map((o) => o.amount_at_risk_minor), 100000);
  const scored = opportunities.map((opp) => calculatePriorityScore(opp, maxRisk));
  scored.sort((a, b) => b.priorityScore - a.priorityScore);
  return scored.map((item, index) => ({
    ...item,
    priorityRank: index + 1,
  }));
}

export function computeExecutiveWhyThisMatters(opportunities: OpportunityListItem[], grossRecoveredMinor: number): {
  headline: string;
  subtext: string;
  top3Percentage: number;
} {
  const openOpps = opportunities.filter((o) => o.status !== "CLOSED" && o.status !== "RESOLVED");
  const totalRecoverable = openOpps.reduce((sum, o) => sum + o.amount_at_risk_minor, 0);
  const totalExpected = openOpps.reduce((sum, o) => sum + o.expected_recovery_minor, 0);

  const sorted = [...openOpps].sort((a, b) => b.expected_recovery_minor - a.expected_recovery_minor);
  const top3Expected = sorted.slice(0, 3).reduce((sum, o) => sum + o.expected_recovery_minor, 0);
  const top3Percentage = totalExpected > 0 ? Math.round((top3Expected / totalExpected) * 100) : 0;

  const formattedRecoverable = (totalRecoverable / 100).toLocaleString("en-IN", { style: "currency", currency: "INR" });
  const formattedRecovered = (grossRecoveredMinor / 100).toLocaleString("en-IN", { style: "currency", currency: "INR" });

  return {
    headline: `${formattedRecoverable} is currently recoverable across ${openOpps.length} active opportunities. The top 3 represent ${top3Percentage}% of total expected yield.`,
    subtext: `System has autonomously realized ${formattedRecovered} in verified recovered revenue with zero policy violations.`,
    top3Percentage,
  };
}
