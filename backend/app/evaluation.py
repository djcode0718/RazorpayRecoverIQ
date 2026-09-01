import random
import uuid
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import EvaluationCase, EvaluationResult


@dataclass(frozen=True)
class EvaluationRunSummary:
    evaluation_run_id: str
    records: int
    precision: float
    recall: float
    f1: float
    false_positive_rate: float
    revenue_at_risk_minor: int
    recoverable_revenue_minor: int
    gross_recovered_minor: int
    intervention_cost_minor: int
    net_recovered_minor: int
    recovery_rate: float
    false_positive_count: int
    false_positive_exposure_minor: int
    false_positive_intervention_cost_minor: int
    allowed_count: int
    blocked_count: int
    escalated_count: int
    failed_count: int


StrategyPredictor = Callable[[EvaluationCase], tuple[bool, str, int, str]]


def _clamp_probability(value: int) -> int:
    return max(0, min(100, value))


def _baseline_prediction(case: EvaluationCase) -> tuple[bool, str, int, str]:
    is_failure = bool(case.failure_features.get("is_failure"))
    predicted_recoverable = is_failure
    predicted_action = "RECOVERY_PROMPT" if predicted_recoverable else "NO_ACTION"
    predicted_probability = 75 if predicted_recoverable else 10
    reason_code = "BASELINE_FAILED_PAYMENT_RULE" if predicted_recoverable else "BASELINE_NON_FAILURE"
    return predicted_recoverable, predicted_action, predicted_probability, reason_code


def _recoveriq_policy_prediction(case: EvaluationCase) -> tuple[bool, str, int, str]:
    is_failure = bool(case.failure_features.get("is_failure"))
    if not is_failure:
        return False, "NO_ACTION", 5, "NO_FAILURE_SIGNAL"

    amount_minor = int(case.payment_features.get("amount_minor", 0))
    reason = str(case.failure_features.get("reason") or "").lower()
    segment = str(case.customer_features.get("segment") or "").lower()
    attempts = int(case.customer_features.get("attempts") or 0)
    success_count = int(case.customer_features.get("success_count") or 0)
    failed_count = int(case.history_features.get("failed_count") or max(0, attempts - success_count))

    score = 35
    if segment == "vip":
        score += 20
    elif segment == "regular":
        score += 10
    elif segment == "at_risk":
        score -= 12

    if success_count >= failed_count + 2:
        score += 15
    elif success_count >= failed_count:
        score += 5
    else:
        score -= 10

    if amount_minor <= 400_000:
        score += 10
    elif amount_minor >= 800_000:
        score -= 10

    if reason in {"network", "3ds_failed"}:
        score += 12
    elif reason == "insufficient_funds":
        score -= 8
    elif reason == "issuer_declined":
        score -= 6

    probability = _clamp_probability(score)
    predicted_recoverable = probability >= 60

    # Policy path: strict allowance criteria keeps high-risk retries constrained.
    allow_execution = predicted_recoverable and probability >= 65 and amount_minor <= 900_000
    predicted_action = "RECOVERY_PROMPT" if allow_execution else "NO_ACTION"

    if probability < 60:
        reason_code = "SCORE_BELOW_RECOVERABLE_THRESHOLD"
    elif probability < 65:
        reason_code = "POLICY_CONFIDENCE_GUARDRAIL"
    elif amount_minor > 900_000:
        reason_code = "POLICY_MAX_AMOUNT_GUARDRAIL"
    else:
        reason_code = "POLICY_ALLOW_EXECUTION"

    return predicted_recoverable, predicted_action, probability, reason_code


def _summary_and_attribution_from_predictions(
    *,
    run_id: str,
    cases: list[EvaluationCase],
    predictor: StrategyPredictor,
    intervention_cost_minor_for_action,
) -> tuple[EvaluationRunSummary, dict]:
    summary = _summary_from_predictions(
        run_id=run_id,
        cases=cases,
        predictor=predictor,
        intervention_cost_minor_for_action=intervention_cost_minor_for_action,
    )

    action_counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    recoverable_positive = 0

    for case in cases:
        predicted_recoverable, predicted_action, _, reason_code = predictor(case)
        action_counts[predicted_action] = action_counts.get(predicted_action, 0) + 1
        reason_counts[reason_code] = reason_counts.get(reason_code, 0) + 1
        if predicted_recoverable:
            recoverable_positive += 1

    attribution = {
        "action_counts": action_counts,
        "policy_reason_counts": reason_counts,
        "predicted_recoverable_count": recoverable_positive,
        "predicted_non_recoverable_count": len(cases) - recoverable_positive,
    }
    return summary, attribution


def _summary_from_predictions(
    *,
    run_id: str,
    cases: list[EvaluationCase],
    predictor: StrategyPredictor,
    intervention_cost_minor_for_action,
) -> EvaluationRunSummary:
    tp = fp = fn = tn = 0
    revenue_at_risk = recoverable_revenue = gross_recovered = intervention_cost = 0
    false_positive_count = false_positive_exposure = false_positive_intervention_cost = 0
    allowed_count = blocked_count = escalated_count = failed_count = 0

    for case in cases:
        predicted_recoverable, predicted_action, _, _ = predictor(case)
        actual_recoverable = bool(case.ground_truth_recoverable)
        is_failure = bool(case.failure_features.get("is_failure"))

        if predicted_recoverable and actual_recoverable:
            tp += 1
        elif predicted_recoverable and not actual_recoverable:
            fp += 1
            false_positive_count += 1
        elif (not predicted_recoverable) and actual_recoverable:
            fn += 1
        else:
            tn += 1

        normalized_action = (predicted_action or "NO_ACTION").upper()
        if normalized_action == "ESCALATE":
            escalated_count += 1
        elif normalized_action == "NO_ACTION":
            blocked_count += 1
        else:
            allowed_count += 1

        if (predicted_recoverable and not actual_recoverable) or ((not predicted_recoverable) and actual_recoverable):
            failed_count += 1

        amount = int(case.payment_features.get("amount_minor", 0))
        if is_failure:
            revenue_at_risk += amount
        if actual_recoverable:
            recoverable_revenue += int(case.ground_truth_recovered_amount_minor)

        recovered = int(case.ground_truth_recovered_amount_minor) if predicted_recoverable and actual_recoverable else 0
        cost = intervention_cost_minor_for_action(predicted_action)
        gross_recovered += recovered
        intervention_cost += cost
        if predicted_recoverable and not actual_recoverable:
            false_positive_exposure += amount
            false_positive_intervention_cost += cost

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    false_positive_rate = fp / (fp + tn) if (fp + tn) else 0.0
    recovery_rate = gross_recovered / recoverable_revenue if recoverable_revenue else 0.0

    return EvaluationRunSummary(
        evaluation_run_id=run_id,
        records=len(cases),
        precision=precision,
        recall=recall,
        f1=f1,
        false_positive_rate=false_positive_rate,
        revenue_at_risk_minor=revenue_at_risk,
        recoverable_revenue_minor=recoverable_revenue,
        gross_recovered_minor=gross_recovered,
        intervention_cost_minor=intervention_cost,
        net_recovered_minor=gross_recovered - intervention_cost,
        recovery_rate=recovery_rate,
        false_positive_count=false_positive_count,
        false_positive_exposure_minor=false_positive_exposure,
        false_positive_intervention_cost_minor=false_positive_intervention_cost,
        allowed_count=allowed_count,
        blocked_count=blocked_count,
        escalated_count=escalated_count,
        failed_count=failed_count,
    )


def evaluation_summary_to_dict(summary: EvaluationRunSummary) -> dict:
    return {
        "evaluation_run_id": summary.evaluation_run_id,
        "records": summary.records,
        "precision": summary.precision,
        "recall": summary.recall,
        "f1": summary.f1,
        "false_positive_rate": summary.false_positive_rate,
        "revenue_at_risk_minor": summary.revenue_at_risk_minor,
        "recoverable_revenue_minor": summary.recoverable_revenue_minor,
        "gross_recovered_minor": summary.gross_recovered_minor,
        "intervention_cost_minor": summary.intervention_cost_minor,
        "net_recovered_minor": summary.net_recovered_minor,
        "recovery_rate": summary.recovery_rate,
        "false_positive_count": summary.false_positive_count,
        "false_positive_exposure_minor": summary.false_positive_exposure_minor,
        "false_positive_intervention_cost_minor": summary.false_positive_intervention_cost_minor,
        "operational": {
            "allowed": summary.allowed_count,
            "blocked": summary.blocked_count,
            "escalated": summary.escalated_count,
            "failed": summary.failed_count,
        },
    }


def generate_synthetic_cases(
    db: Session,
    *,
    dataset_version: str,
    generation_seed: int,
    total_cases: int = 1000,
) -> dict[str, int]:
    rng = random.Random(generation_seed)
    db.execute(delete(EvaluationCase).where(EvaluationCase.dataset_version == dataset_version))
    db.commit()

    dev_count = int(total_cases * 0.70)
    val_count = int(total_cases * 0.15)
    test_count = total_cases - dev_count - val_count

    for idx in range(total_cases):
        amount = rng.randint(10_000, 1_000_000)
        attempts = rng.randint(1, 24)
        success_count = rng.randint(0, attempts)
        fail_count = attempts - success_count
        segment = rng.choice(["new", "regular", "vip", "at_risk"])
        is_failure = rng.random() < 0.65
        failure_reason = rng.choice(["issuer_declined", "network", "insufficient_funds", "3ds_failed"])

        latent = (
            (0.3 if segment == "vip" else 0.0)
            + (0.2 if success_count > fail_count else -0.2)
            + (0.1 if amount < 400_000 else -0.1)
            + rng.uniform(-0.25, 0.25)
        )
        ground_truth_recoverable = is_failure and latent > 0.05
        recovered_amount = int(amount * (0.6 if ground_truth_recoverable else 0.0))
        ground_truth_action = "RECOVERY_PROMPT" if ground_truth_recoverable else "NO_ACTION"

        if idx < dev_count:
            split = "DEVELOPMENT"
        elif idx < dev_count + val_count:
            split = "VALIDATION"
        else:
            split = "TEST"

        case = EvaluationCase(
            dataset_version=dataset_version,
            generation_seed=generation_seed,
            case_type="failed_payment" if is_failure else "successful_payment",
            customer_features={"segment": segment, "attempts": attempts, "success_count": success_count},
            payment_features={"amount_minor": amount, "currency": "INR"},
            failure_features={"reason": failure_reason, "is_failure": is_failure},
            history_features={"failed_count": fail_count},
            ground_truth_recoverable=ground_truth_recoverable,
            ground_truth_action=ground_truth_action,
            ground_truth_recovered_amount_minor=recovered_amount,
            split=split,
        )
        db.add(case)

    db.commit()
    return {"total": total_cases, "development": dev_count, "validation": val_count, "test": test_count}


def run_baseline_evaluation(
    db: Session,
    *,
    dataset_version: str,
    split: str = "TEST",
    evaluation_run_id: str | None = None,
) -> EvaluationRunSummary:
    run_id = evaluation_run_id or str(uuid.uuid4())
    db.execute(delete(EvaluationResult).where(EvaluationResult.evaluation_run_id == run_id))
    db.commit()
    cases = db.execute(
        select(EvaluationCase).where(EvaluationCase.dataset_version == dataset_version).where(EvaluationCase.split == split)
    ).scalars().all()

    tp = fp = fn = tn = 0
    revenue_at_risk = recoverable_revenue = gross_recovered = intervention_cost = 0
    false_positive_count = false_positive_exposure = false_positive_intervention_cost = 0
    allowed_count = blocked_count = escalated_count = failed_count = 0

    for case in cases:
        is_failure = bool(case.failure_features.get("is_failure"))
        predicted_recoverable = is_failure
        predicted_action = "RECOVERY_PROMPT" if predicted_recoverable else "NO_ACTION"
        predicted_probability = 75 if predicted_recoverable else 10

        actual_recoverable = bool(case.ground_truth_recoverable)
        correct = predicted_recoverable == actual_recoverable
        false_positive = predicted_recoverable and not actual_recoverable
        false_negative = (not predicted_recoverable) and actual_recoverable

        if predicted_recoverable and actual_recoverable:
            tp += 1
        elif predicted_recoverable and not actual_recoverable:
            fp += 1
            false_positive_count += 1
        elif (not predicted_recoverable) and actual_recoverable:
            fn += 1
        else:
            tn += 1

        normalized_action = (predicted_action or "NO_ACTION").upper()
        if normalized_action == "ESCALATE":
            escalated_count += 1
        elif normalized_action == "NO_ACTION":
            blocked_count += 1
        else:
            allowed_count += 1
        if false_positive or false_negative:
            failed_count += 1

        amount = int(case.payment_features.get("amount_minor", 0))
        if is_failure:
            revenue_at_risk += amount
        if actual_recoverable:
            recoverable_revenue += int(case.ground_truth_recovered_amount_minor)

        recovered = int(case.ground_truth_recovered_amount_minor) if predicted_recoverable and actual_recoverable else 0
        cost = 500 if predicted_recoverable else 0
        net = recovered - cost
        gross_recovered += recovered
        intervention_cost += cost
        if false_positive:
            false_positive_exposure += amount
            false_positive_intervention_cost += cost

        result = EvaluationResult(
            evaluation_run_id=run_id,
            case_id=case.id,
            predicted_recoverable=predicted_recoverable,
            predicted_action=predicted_action,
            predicted_probability=predicted_probability,
            actual_recoverable=actual_recoverable,
            actual_action=case.ground_truth_action,
            correct=correct,
            false_positive=false_positive,
            false_negative=false_negative,
            recovered_amount_minor=recovered,
            intervention_cost_minor=cost,
            net_recovered_amount_minor=net,
        )
        db.add(result)

    db.commit()

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    false_positive_rate = fp / (fp + tn) if (fp + tn) else 0.0
    recovery_rate = gross_recovered / recoverable_revenue if recoverable_revenue else 0.0

    return EvaluationRunSummary(
        evaluation_run_id=run_id,
        records=len(cases),
        precision=precision,
        recall=recall,
        f1=f1,
        false_positive_rate=false_positive_rate,
        revenue_at_risk_minor=revenue_at_risk,
        recoverable_revenue_minor=recoverable_revenue,
        gross_recovered_minor=gross_recovered,
        intervention_cost_minor=intervention_cost,
        net_recovered_minor=gross_recovered - intervention_cost,
        recovery_rate=recovery_rate,
        false_positive_count=false_positive_count,
        false_positive_exposure_minor=false_positive_exposure,
        false_positive_intervention_cost_minor=false_positive_intervention_cost,
        allowed_count=allowed_count,
        blocked_count=blocked_count,
        escalated_count=escalated_count,
        failed_count=failed_count,
    )


def get_evaluation_run_cases(db: Session, *, evaluation_run_id: str) -> list[EvaluationCase]:
    results = db.execute(
        select(EvaluationResult).where(EvaluationResult.evaluation_run_id == evaluation_run_id)
    ).scalars().all()
    if not results:
        return []

    case_ids = [result.case_id for result in results]
    return list(db.execute(select(EvaluationCase).where(EvaluationCase.id.in_(case_ids))).scalars().all())


def get_recoveriq_policy_path_summary(
    db: Session,
    *,
    evaluation_run_id: str,
) -> EvaluationRunSummary | None:
    cases = get_evaluation_run_cases(db, evaluation_run_id=evaluation_run_id)
    if not cases:
        return None

    return _summary_from_predictions(
        run_id=f"{evaluation_run_id}:recoveriq_policy",
        cases=cases,
        predictor=_recoveriq_policy_prediction,
        intervention_cost_minor_for_action=lambda action: 450 if action != "NO_ACTION" else 0,
    )


def run_recoveriq_evaluation(
    db: Session,
    *,
    dataset_version: str,
    split: str = "TEST",
    evaluation_run_id: str | None = None,
) -> EvaluationRunSummary:
    run_id = evaluation_run_id or str(uuid.uuid4())
    cases = list(
        db.execute(
            select(EvaluationCase).where(EvaluationCase.dataset_version == dataset_version).where(EvaluationCase.split == split)
        ).scalars().all()
    )
    return _summary_from_predictions(
        run_id=run_id,
        cases=cases,
        predictor=_recoveriq_policy_prediction,
        intervention_cost_minor_for_action=lambda action: 450 if action != "NO_ACTION" else 0,
    )


def get_strategy_attribution_comparison(
    db: Session,
    *,
    evaluation_run_id: str,
) -> dict | None:
    cases = get_evaluation_run_cases(db, evaluation_run_id=evaluation_run_id)
    if not cases:
        return None

    baseline_summary, baseline_attribution = _summary_and_attribution_from_predictions(
        run_id=evaluation_run_id,
        cases=cases,
        predictor=_baseline_prediction,
        intervention_cost_minor_for_action=lambda action: 500 if action != "NO_ACTION" else 0,
    )
    recoveriq_summary, recoveriq_attribution = _summary_and_attribution_from_predictions(
        run_id=f"{evaluation_run_id}:recoveriq_policy",
        cases=cases,
        predictor=_recoveriq_policy_prediction,
        intervention_cost_minor_for_action=lambda action: 450 if action != "NO_ACTION" else 0,
    )

    baseline_actions = baseline_attribution["action_counts"]
    recoveriq_actions = recoveriq_attribution["action_counts"]
    all_actions = sorted(set(baseline_actions.keys()) | set(recoveriq_actions.keys()))
    action_level_deltas = {
        action: recoveriq_actions.get(action, 0) - baseline_actions.get(action, 0)
        for action in all_actions
    }

    baseline_reasons = baseline_attribution["policy_reason_counts"]
    recoveriq_reasons = recoveriq_attribution["policy_reason_counts"]
    all_reasons = sorted(set(baseline_reasons.keys()) | set(recoveriq_reasons.keys()))
    policy_reason_deltas = {
        reason: recoveriq_reasons.get(reason, 0) - baseline_reasons.get(reason, 0)
        for reason in all_reasons
    }

    return {
        "baseline_summary": baseline_summary,
        "recoveriq_summary": recoveriq_summary,
        "attribution": {
            "baseline": baseline_attribution,
            "recoveriq": recoveriq_attribution,
            "action_level_deltas": action_level_deltas,
            "policy_reason_deltas": policy_reason_deltas,
        },
    }


def get_evaluation_run_summary(db: Session, *, evaluation_run_id: str) -> EvaluationRunSummary | None:
    results = db.execute(
        select(EvaluationResult).where(EvaluationResult.evaluation_run_id == evaluation_run_id)
    ).scalars().all()
    if not results:
        return None

    case_ids = [result.case_id for result in results]
    cases = db.execute(select(EvaluationCase).where(EvaluationCase.id.in_(case_ids))).scalars().all()
    case_map = {case.id: case for case in cases}

    tp = fp = fn = tn = 0
    revenue_at_risk = recoverable_revenue = gross_recovered = intervention_cost = 0
    false_positive_count = false_positive_exposure = false_positive_intervention_cost = 0
    allowed_count = blocked_count = escalated_count = failed_count = 0

    for result in results:
        if result.predicted_recoverable and result.actual_recoverable:
            tp += 1
        elif result.predicted_recoverable and (not result.actual_recoverable):
            fp += 1
            false_positive_count += 1
        elif (not result.predicted_recoverable) and result.actual_recoverable:
            fn += 1
        else:
            tn += 1

        normalized_action = (result.predicted_action or "NO_ACTION").upper()
        if normalized_action == "ESCALATE":
            escalated_count += 1
        elif normalized_action == "NO_ACTION":
            blocked_count += 1
        else:
            allowed_count += 1
        if result.false_positive or result.false_negative:
            failed_count += 1

        case = case_map.get(result.case_id)
        if case is not None:
            amount_minor = int(case.payment_features.get("amount_minor", 0))
            if bool(case.failure_features.get("is_failure")):
                revenue_at_risk += amount_minor
            if case.ground_truth_recoverable:
                recoverable_revenue += int(case.ground_truth_recovered_amount_minor)
            if result.false_positive:
                false_positive_exposure += amount_minor
                false_positive_intervention_cost += int(result.intervention_cost_minor)

        gross_recovered += int(result.recovered_amount_minor)
        intervention_cost += int(result.intervention_cost_minor)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    false_positive_rate = fp / (fp + tn) if (fp + tn) else 0.0
    recovery_rate = gross_recovered / recoverable_revenue if recoverable_revenue else 0.0

    return EvaluationRunSummary(
        evaluation_run_id=evaluation_run_id,
        records=len(results),
        precision=precision,
        recall=recall,
        f1=f1,
        false_positive_rate=false_positive_rate,
        revenue_at_risk_minor=revenue_at_risk,
        recoverable_revenue_minor=recoverable_revenue,
        gross_recovered_minor=gross_recovered,
        intervention_cost_minor=intervention_cost,
        net_recovered_minor=gross_recovered - intervention_cost,
        recovery_rate=recovery_rate,
        false_positive_count=false_positive_count,
        false_positive_exposure_minor=false_positive_exposure,
        false_positive_intervention_cost_minor=false_positive_intervention_cost,
        allowed_count=allowed_count,
        blocked_count=blocked_count,
        escalated_count=escalated_count,
        failed_count=failed_count,
    )
