from __future__ import annotations

from dataclasses import asdict, dataclass

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .evaluation import generate_synthetic_cases, run_baseline_evaluation
from .models import EvaluationResult, RevenueOpportunity
from .security import redact_sensitive_data


@dataclass(frozen=True)
class ReadinessCheck:
    id: str
    status: str
    message: str
    evidence: dict


def _check_status(overall: str, incoming: str) -> str:
    if incoming == "FAIL":
        return "FAIL"
    if incoming == "PARTIAL" and overall != "FAIL":
        return "PARTIAL"
    return overall


def execute_readiness_acceptance_workflow(db: Session) -> dict:
    checks: list[ReadinessCheck] = []
    overall_status = "PASS"

    db.execute(text("SELECT 1"))
    checks.append(
        ReadinessCheck(
            id="db_connectivity",
            status="PASS",
            message="Database connectivity check succeeded.",
            evidence={"query": "SELECT 1"},
        )
    )

    opportunity_count = db.execute(select(RevenueOpportunity.id)).scalars().all()
    checks.append(
        ReadinessCheck(
            id="opportunity_pipeline_data",
            status="PASS" if len(opportunity_count) > 0 else "PARTIAL",
            message="Opportunity data available for demo views." if opportunity_count else "No opportunities yet; use webhook simulation before demo.",
            evidence={"count": len(opportunity_count)},
        )
    )
    overall_status = _check_status(overall_status, checks[-1].status)

    eval_run_count = db.execute(select(EvaluationResult.evaluation_run_id).distinct()).scalars().all()
    checks.append(
        ReadinessCheck(
            id="evaluation_history_data",
            status="PASS" if len(eval_run_count) > 0 else "PARTIAL",
            message="Evaluation history available." if eval_run_count else "No evaluation runs yet; run one from Evaluation Center.",
            evidence={"distinct_runs": len(eval_run_count)},
        )
    )
    overall_status = _check_status(overall_status, checks[-1].status)

    probe_version = "readiness_probe"
    split_counts = generate_synthetic_cases(db, dataset_version=probe_version, generation_seed=1313, total_cases=40)
    run_a = run_baseline_evaluation(db, dataset_version=probe_version, split="TEST", evaluation_run_id="readiness_probe_a")
    split_counts_repeat = generate_synthetic_cases(db, dataset_version=probe_version, generation_seed=1313, total_cases=40)
    run_b = run_baseline_evaluation(db, dataset_version=probe_version, split="TEST", evaluation_run_id="readiness_probe_b")

    reproducible = (
        split_counts == split_counts_repeat
        and run_a.records == run_b.records
        and run_a.precision == run_b.precision
        and run_a.recall == run_b.recall
        and run_a.f1 == run_b.f1
        and run_a.net_recovered_minor == run_b.net_recovered_minor
    )

    checks.append(
        ReadinessCheck(
            id="reproducibility_probe",
            status="PASS" if reproducible else "FAIL",
            message="Deterministic dataset and baseline metrics are reproducible." if reproducible else "Reproducibility probe diverged.",
            evidence={
                "split_counts": split_counts,
                "run_a": {
                    "records": run_a.records,
                    "precision": run_a.precision,
                    "recall": run_a.recall,
                    "f1": run_a.f1,
                    "net_recovered_minor": run_a.net_recovered_minor,
                },
                "run_b": {
                    "records": run_b.records,
                    "precision": run_b.precision,
                    "recall": run_b.recall,
                    "f1": run_b.f1,
                    "net_recovered_minor": run_b.net_recovered_minor,
                },
            },
        )
    )
    overall_status = _check_status(overall_status, checks[-1].status)

    redaction_result = redact_sensitive_data({"authorization": "abc", "nested": {"phone": "99999", "ok": "y"}})
    redaction_ok = redaction_result.get("authorization") == "[REDACTED]" and redaction_result["nested"].get("phone") == "[REDACTED]"
    checks.append(
        ReadinessCheck(
            id="security_redaction_guard",
            status="PASS" if redaction_ok else "FAIL",
            message="Sensitive data redaction guard is active." if redaction_ok else "Sensitive data redaction guard failed.",
            evidence={"sample_result": redaction_result},
        )
    )
    overall_status = _check_status(overall_status, checks[-1].status)

    return {
        "workflow": "demo_readiness_validation",
        "status": overall_status,
        "checks": [asdict(check) for check in checks],
        "summary": {
            "pass_count": len([check for check in checks if check.status == "PASS"]),
            "partial_count": len([check for check in checks if check.status == "PARTIAL"]),
            "fail_count": len([check for check in checks if check.status == "FAIL"]),
        },
    }


def execute_phase13_acceptance_workflow(db: Session) -> dict:
    # Backward-compatible wrapper retained for existing imports/routes.
    return execute_readiness_acceptance_workflow(db)
