from dataclasses import dataclass


ACTION_COST_MINOR = {
    "CREATE_PAYMENT_LINK": 350,
    "RETRY": 200,
    "DELAYED_RETRY": 300,
    "RECOVERY_PROMPT": 500,
    "ALTERNATE_PAYMENT_PATH": 700,
    "ESCALATE": 1200,
    "NO_ACTION": 0,
}


@dataclass(frozen=True)
class EconomicsResult:
    revenue_at_risk_minor: int
    recovery_probability_pct: int
    expected_recovery_minor: int
    estimated_intervention_cost_minor: int
    expected_net_recovery_minor: int


def estimate_intervention_cost_minor(action: str) -> int:
    return ACTION_COST_MINOR.get(action, 800)


def compute_expected_recovery_minor(amount_at_risk_minor: int, recovery_probability_pct: int) -> int:
    clamped_probability = max(0, min(100, recovery_probability_pct))
    return (amount_at_risk_minor * clamped_probability) // 100


def compute_economics(amount_at_risk_minor: int, recovery_probability_pct: int, action: str) -> EconomicsResult:
    clamped_probability = max(0, min(100, int(recovery_probability_pct)))
    expected_recovery = compute_expected_recovery_minor(amount_at_risk_minor, clamped_probability)
    intervention_cost = estimate_intervention_cost_minor(action)
    return EconomicsResult(
        revenue_at_risk_minor=int(amount_at_risk_minor),
        recovery_probability_pct=clamped_probability,
        expected_recovery_minor=expected_recovery,
        estimated_intervention_cost_minor=intervention_cost,
        expected_net_recovery_minor=expected_recovery - intervention_cost,
    )
