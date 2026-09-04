from datetime import UTC, datetime
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .gateway_adapters import (
    PaymentAdapterAccountLimitError,
    PaymentAdapterConfigurationError,
    PaymentAdapterError,
    PaymentAdapterRateLimitError,
    PaymentAdapterTimeoutError,
    PaymentLinkRequest,
    get_execution_strategy_adapters,
    get_payment_adapter,
)
from .models import AuditEvent, PolicyEvaluation, RecoveryAttempt, RecoveryDecision, RecoveryPaymentLink, RevenueOpportunity
from .security import redact_sensitive_data, sanitize_error_message
from .state_machine import RecoveryState, can_transition_recovery


EXECUTOR_VERSION = "v1.0"
EXECUTABLE_ACTIONS = {"CREATE_PAYMENT_LINK"}
TERMINAL_OPPORTUNITY_STATUSES = {"CLOSED", "RESOLVED"}
_LEGACY_LINK_EQUIVALENT_ACTIONS = {
    "RETRY",
    "DELAYED_RETRY",
    "RECOVERY_PROMPT",
    "ALTERNATE_PAYMENT_PATH",
}


def _normalize_executable_action(action: str) -> str:
    normalized = (action or "").strip().upper()
    if normalized in _LEGACY_LINK_EQUIVALENT_ACTIONS:
        return "CREATE_PAYMENT_LINK"
    return normalized


def _utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _record_failure(
    db: Session,
    attempt: RecoveryAttempt,
    exc: Exception,
    failure_code: str,
    retryable: bool,
    *,
    opportunity_id: int,
    attempt_number: int,
    correlation_id: str,
    provider: str,
    execution_strategy: str,
    adapter_name: str,
    policy: PolicyEvaluation,
    started_at: datetime,
    retry_after: int | None = None,
) -> None:
    completed_at = _utc_now_naive()
    duration_ms = max(0, int((completed_at - started_at).total_seconds() * 1000))
    sanitized_err = sanitize_error_message(str(exc))
    attempt.status = "FAILED"
    attempt.completed_at = completed_at
    attempt.failure_code = failure_code
    attempt.failure_reason = sanitized_err

    meta = {
        "provider": provider,
        "execution_strategy": execution_strategy,
        "adapter": adapter_name,
        "operation": "PAYMENT_LINK_CREATE",
        "opportunity_id": opportunity_id,
        "recovery_attempt_id": attempt.id,
        "attempt_number": attempt_number,
        "correlation_id": correlation_id,
        "policy_decision": policy.result,
        "policy_version": policy.policy_version,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "duration_ms": duration_ms,
        "outcome": "FAILED",
        "retryable": retryable,
        "error_code": failure_code,
        "sanitized_error_message": sanitized_err,
    }
    if retry_after is not None:
        meta["retry_after_seconds"] = retry_after

    audit_event = AuditEvent(
        event_type="recovery.attempt.failed",
        actor_type="RECOVERY_EXECUTOR",
        actor_id=f"{adapter_name}:{EXECUTOR_VERSION}",
        entity_type="RecoveryAttempt",
        entity_id=str(attempt.id),
        correlation_id=correlation_id,
        result="FAILED",
        reason=sanitized_err,
        metadata_json=meta,
        outcome_snapshot={
            "status": "FAILED",
            "error_code": failure_code,
            "retryable": retryable,
        },
    )
    db.add(audit_event)
    db.commit()


def execute_recovery_attempt(
    db: Session,
    *,
    opportunity_id: int,
    decision_id: int,
    policy_evaluation_id: int,
) -> RecoveryAttempt:
    policy = db.execute(select(PolicyEvaluation).where(PolicyEvaluation.id == policy_evaluation_id)).scalar_one()
    if policy.result != "ALLOW":
        raise ValueError("policy_not_allow")

    opportunity = db.execute(
        select(RevenueOpportunity).where(RevenueOpportunity.id == opportunity_id)
    ).scalar_one()
    decision = db.execute(select(RecoveryDecision).where(RecoveryDecision.id == decision_id)).scalar_one()

    if opportunity.status in TERMINAL_OPPORTUNITY_STATUSES:
        raise ValueError("opportunity_not_executable")

    executable_action = _normalize_executable_action(decision.recommended_action)
    if executable_action not in EXECUTABLE_ACTIONS:
        raise ValueError("action_not_executable")

    if not decision.schema_version:
        raise ValueError("invalid_ai_decision_schema")

    settings = get_settings()
    if settings.app_mode.strip().lower() not in {"simulation", "test", "development"}:
        raise ValueError("execution_requires_test_mode")

    known_states = {item.value for item in RecoveryState}
    if opportunity.status in known_states and not can_transition_recovery(opportunity.status, "PAYMENT_LINK_CREATED"):
        raise ValueError("invalid_recovery_state_transition")

    open_attempt = db.execute(
        select(RecoveryAttempt)
        .where(
            RecoveryAttempt.opportunity_id == opportunity_id,
            RecoveryAttempt.status.in_({"REQUESTED", "EXECUTED", "PENDING_VERIFICATION"}),
        )
        .order_by(RecoveryAttempt.attempt_number.desc(), RecoveryAttempt.id.desc())
    ).scalars().first()
    if open_attempt is not None:
        existing_link = db.execute(
            select(RecoveryPaymentLink).where(RecoveryPaymentLink.recovery_attempt_id == open_attempt.id)
        ).scalars().first()

        adapter_mode = str(getattr(settings, "payment_adapter_mode", "simulation")).strip().lower()
        if existing_link is not None:
            raw_data = json.loads(existing_link.external_response_reference or "{}") if existing_link.external_response_reference else {}
            has_live_link = bool(raw_data.get("short_url")) or existing_link.payment_link_id.startswith("plink_T")
            if has_live_link or adapter_mode == "simulation":
                return open_attempt

    attempt_number = db.execute(
        select(func.count(RecoveryAttempt.id)).where(RecoveryAttempt.opportunity_id == opportunity_id)
    ).scalar_one() + 1

    attempt = RecoveryAttempt(
        opportunity_id=opportunity_id,
        action=executable_action,
        attempt_number=attempt_number,
        policy_evaluation_id=policy_evaluation_id,
        status="REQUESTED",
        amount_minor=opportunity.amount_at_risk_minor,
        currency=opportunity.currency,
        failure_code=None,
        failure_reason=None,
        verified_outcome=None,
        recovered_amount_minor=0,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    # Resolve primary and fallback adapters based on configured strategy
    custom_adapter = None
    try:
        custom_adapter = get_payment_adapter(settings)
    except Exception:
        pass

    try:
        primary_adapter, fallback_adapter, strategy_name = get_execution_strategy_adapters(settings)
    except Exception:
        if custom_adapter is not None:
            primary_adapter = custom_adapter
            fallback_adapter = None
            strategy_name = getattr(custom_adapter, "name", "CUSTOM").upper()
        else:
            raise

    # If get_payment_adapter was monkeypatched on this module or returned a distinct adapter, honor it
    if custom_adapter is not None and type(custom_adapter) is not type(primary_adapter):
        primary_adapter = custom_adapter
        fallback_adapter = None
        strategy_name = getattr(custom_adapter, "name", "CUSTOM").upper()

    primary_name = getattr(primary_adapter, "name", "unknown")
    execution_strategy = (
        "MCP" if primary_name in {"razorpay_mcp", "mcp"}
        else ("DIRECT_REST" if primary_name in {"razorpay_test", "test_mode"} else "SIMULATION")
    )
    provider = "razorpay" if execution_strategy in {"MCP", "DIRECT_REST"} else "simulation"
    operation = "PAYMENT_LINK_CREATE"
    correlation_id = f"opp_{opportunity_id}_att_{attempt_number}"

    started_at = _utc_now_naive()

    # 1. Audit event: RECOVERY_EXECUTION_STARTED
    audit_start = AuditEvent(
        event_type="recovery.execution.started",
        actor_type="RECOVERY_EXECUTOR",
        actor_id=f"{primary_name}:{EXECUTOR_VERSION}",
        entity_type="RecoveryAttempt",
        entity_id=str(attempt.id),
        correlation_id=correlation_id,
        result="STARTED",
        metadata_json={
            "provider": provider,
            "execution_strategy": execution_strategy,
            "strategy_name": strategy_name,
            "adapter": primary_name,
            "has_fallback": fallback_adapter is not None,
            "fallback_adapter": getattr(fallback_adapter, "name", None),
            "operation": operation,
            "opportunity_id": opportunity_id,
            "recovery_attempt_id": attempt.id,
            "attempt_number": attempt_number,
            "correlation_id": correlation_id,
            "policy_decision": policy.result,
            "policy_version": policy.policy_version,
            "started_at": started_at.isoformat(),
            "amount_minor": opportunity.amount_at_risk_minor,
            "currency": opportunity.currency,
        },
        input_snapshot={
            "opportunity_id": opportunity_id,
            "amount_minor": opportunity.amount_at_risk_minor,
            "currency": opportunity.currency,
            "customer_id": str(opportunity.customer_id) if opportunity.customer_id else None,
            "recommended_action": decision.recommended_action,
            "confidence": decision.confidence,
            "diagnosis": decision.diagnosis,
        },
        policy_snapshot={
            "policy_evaluation_id": policy.id,
            "result": policy.result,
            "policy_version": policy.policy_version,
            "reason_codes": policy.reason_codes,
        },
        decision_snapshot={
            "decision_id": decision.id,
            "recommended_action": decision.recommended_action,
            "confidence": decision.confidence,
            "diagnosis": decision.diagnosis,
        },
    )
    db.add(audit_start)
    db.commit()

    req = PaymentLinkRequest(
        opportunity_id=opportunity_id,
        attempt_number=attempt_number,
        amount_minor=opportunity.amount_at_risk_minor,
        currency=opportunity.currency,
        customer_reference=str(opportunity.customer_id) if opportunity.customer_id is not None else None,
    )

    link_result = None
    final_adapter = primary_adapter
    used_fallback = False
    reconciled = False

    try:
        link_result = primary_adapter.create_payment_link(req)
    except PaymentAdapterTimeoutError as primary_timeout:
        # TIMEOUT on primary is AMBIGUOUS -> Reconcile before doing anything
        audit_reconcile = AuditEvent(
            event_type="recovery.reconciliation.attempted",
            actor_type="RECOVERY_EXECUTOR",
            actor_id=f"{primary_name}:{EXECUTOR_VERSION}",
            entity_type="RecoveryAttempt",
            entity_id=str(attempt.id),
            correlation_id=correlation_id,
            result="ATTEMPTED",
            reason="primary_timeout_requires_reconciliation",
            metadata_json={
                "strategy": strategy_name,
                "primary_adapter": primary_name,
                "reference_id": f"recoveriq_{opportunity_id}_{attempt_number}",
            },
        )
        db.add(audit_reconcile)
        db.commit()

        fetch_fn = getattr(primary_adapter, "fetch_payment_link_by_reference", None)
        reconciled_link = fetch_fn(f"recoveriq_{opportunity_id}_{attempt_number}") if callable(fetch_fn) else None
        if reconciled_link is not None:
            link_result = reconciled_link
            reconciled = True
            audit_resolved = AuditEvent(
                event_type="recovery.reconciliation.resolved",
                actor_type="RECOVERY_EXECUTOR",
                actor_id=f"{primary_name}:{EXECUTOR_VERSION}",
                entity_type="RecoveryAttempt",
                entity_id=str(attempt.id),
                correlation_id=correlation_id,
                result="RESOLVED",
                metadata_json={
                    "reconciliation_result": "link_found",
                    "payment_link_id": reconciled_link.payment_link_id,
                    "fallback_attempted": False,
                },
            )
            db.add(audit_resolved)
            db.commit()
        else:
            audit_blocked = AuditEvent(
                event_type="recovery.reconciliation.blocked",
                actor_type="RECOVERY_EXECUTOR",
                actor_id=f"{primary_name}:{EXECUTOR_VERSION}",
                entity_type="RecoveryAttempt",
                entity_id=str(attempt.id),
                correlation_id=correlation_id,
                result="BLOCKED",
                reason="ambiguous_provider_outcome_prevents_fallback",
                metadata_json={
                    "fallback_prevented": True,
                    "reason": "ambiguous_outcome_requires_reconciliation",
                },
            )
            db.add(audit_blocked)
            _record_failure(
                db, attempt, primary_timeout, "ADAPTER_TIMEOUT", True,
                opportunity_id=opportunity_id, attempt_number=attempt_number,
                correlation_id=correlation_id, provider=provider,
                execution_strategy=execution_strategy, adapter_name=primary_name,
                policy=policy, started_at=started_at,
            )
            raise ValueError("adapter_timeout") from primary_timeout

    except (PaymentAdapterRateLimitError, PaymentAdapterAccountLimitError, PaymentAdapterConfigurationError, PaymentAdapterError) as primary_exc:
        if fallback_adapter is not None and getattr(fallback_adapter, "name", None) != primary_name:
            fallback_name = getattr(fallback_adapter, "name", "unknown")
            audit_fallback = AuditEvent(
                event_type="recovery.fallback.triggered",
                actor_type="RECOVERY_EXECUTOR",
                actor_id=f"{primary_name}:{EXECUTOR_VERSION}",
                entity_type="RecoveryAttempt",
                entity_id=str(attempt.id),
                correlation_id=correlation_id,
                result="TRIGGERED",
                reason=sanitize_error_message(str(primary_exc)),
                metadata_json={
                    "original_strategy": strategy_name,
                    "primary_adapter": primary_name,
                    "fallback_adapter": fallback_name,
                    "fallback_eligible": True,
                    "primary_error": sanitize_error_message(str(primary_exc)),
                },
            )
            db.add(audit_fallback)
            db.commit()

            try:
                link_result = fallback_adapter.create_payment_link(req)
                final_adapter = fallback_adapter
                used_fallback = True
            except PaymentAdapterTimeoutError as fb_timeout:
                reconciled_link = fallback_adapter.fetch_payment_link_by_reference(f"recoveriq_{opportunity_id}_{attempt_number}")
                if reconciled_link is not None:
                    link_result = reconciled_link
                    final_adapter = fallback_adapter
                    used_fallback = True
                    reconciled = True
                else:
                    _record_failure(
                        db, attempt, fb_timeout, "ADAPTER_TIMEOUT", True,
                        opportunity_id=opportunity_id, attempt_number=attempt_number,
                        correlation_id=correlation_id, provider=provider,
                        execution_strategy="FALLBACK", adapter_name=fallback_name,
                        policy=policy, started_at=started_at,
                    )
                    raise ValueError("adapter_timeout") from fb_timeout
            except PaymentAdapterRateLimitError as fb_exc:
                _record_failure(
                    db, attempt, fb_exc, "RATE_LIMIT_EXCEEDED", True,
                    opportunity_id=opportunity_id, attempt_number=attempt_number,
                    correlation_id=correlation_id, provider=provider,
                    execution_strategy="FALLBACK", adapter_name=fallback_name,
                    policy=policy, started_at=started_at,
                    retry_after=getattr(fb_exc, "retry_after_seconds", 5),
                )
                raise
            except PaymentAdapterAccountLimitError as fb_exc:
                _record_failure(
                    db, attempt, fb_exc, "GATEWAY_ACCOUNT_LIMIT", False,
                    opportunity_id=opportunity_id, attempt_number=attempt_number,
                    correlation_id=correlation_id, provider=provider,
                    execution_strategy="FALLBACK", adapter_name=fallback_name,
                    policy=policy, started_at=started_at,
                )
                raise
            except PaymentAdapterConfigurationError as fb_exc:
                _record_failure(
                    db, attempt, fb_exc, "ADAPTER_CONFIG", False,
                    opportunity_id=opportunity_id, attempt_number=attempt_number,
                    correlation_id=correlation_id, provider=provider,
                    execution_strategy="FALLBACK", adapter_name=fallback_name,
                    policy=policy, started_at=started_at,
                )
                raise ValueError("adapter_configuration_error") from fb_exc
            except PaymentAdapterError as fb_exc:
                _record_failure(
                    db, attempt, fb_exc, "ADAPTER_ERROR", False,
                    opportunity_id=opportunity_id, attempt_number=attempt_number,
                    correlation_id=correlation_id, provider=provider,
                    execution_strategy="FALLBACK", adapter_name=fallback_name,
                    policy=policy, started_at=started_at,
                )
                raise ValueError(str(fb_exc)) from fb_exc
        else:
            if isinstance(primary_exc, PaymentAdapterRateLimitError):
                _record_failure(
                    db, attempt, primary_exc, "RATE_LIMIT_EXCEEDED", True,
                    opportunity_id=opportunity_id, attempt_number=attempt_number,
                    correlation_id=correlation_id, provider=provider,
                    execution_strategy=execution_strategy, adapter_name=primary_name,
                    policy=policy, started_at=started_at,
                    retry_after=getattr(primary_exc, "retry_after_seconds", 5),
                )
                raise
            elif isinstance(primary_exc, PaymentAdapterAccountLimitError):
                _record_failure(
                    db, attempt, primary_exc, "GATEWAY_ACCOUNT_LIMIT", False,
                    opportunity_id=opportunity_id, attempt_number=attempt_number,
                    correlation_id=correlation_id, provider=provider,
                    execution_strategy=execution_strategy, adapter_name=primary_name,
                    policy=policy, started_at=started_at,
                )
                raise
            elif isinstance(primary_exc, PaymentAdapterConfigurationError):
                _record_failure(
                    db, attempt, primary_exc, "ADAPTER_CONFIG", False,
                    opportunity_id=opportunity_id, attempt_number=attempt_number,
                    correlation_id=correlation_id, provider=provider,
                    execution_strategy=execution_strategy, adapter_name=primary_name,
                    policy=policy, started_at=started_at,
                )
                raise ValueError("adapter_configuration_error") from primary_exc
            else:
                _record_failure(
                    db, attempt, primary_exc, "ADAPTER_ERROR", False,
                    opportunity_id=opportunity_id, attempt_number=attempt_number,
                    correlation_id=correlation_id, provider=provider,
                    execution_strategy=execution_strategy, adapter_name=primary_name,
                    policy=policy, started_at=started_at,
                )
                raise ValueError(str(primary_exc)) from primary_exc

    completed_at = _utc_now_naive()
    duration_ms = max(0, int((completed_at - started_at).total_seconds() * 1000))

    final_strategy = "MCP" if final_adapter.name in {"razorpay_mcp", "mcp"} else ("DIRECT_REST" if final_adapter.name in {"razorpay_test", "test_mode"} else "SIMULATION")

    attempt.status = "EXECUTED"
    attempt.executed_at = started_at
    attempt.completed_at = completed_at
    attempt.external_reference = link_result.payment_link_id
    attempt.failure_code = None
    attempt.failure_reason = None
    opportunity.status = "PAYMENT_LINK_CREATED"
    opportunity.updated_at = completed_at

    link = RecoveryPaymentLink(
        opportunity_id=opportunity_id,
        recovery_attempt_id=attempt.id,
        payment_link_id=link_result.payment_link_id,
        payment_link_reference_id=link_result.reference_id,
        amount_minor=opportunity.amount_at_risk_minor,
        currency=opportunity.currency,
        status=link_result.status,
        external_response_reference=json.dumps({
            "adapter": link_result.provider,
            "execution_strategy": final_strategy,
            "executor_version": EXECUTOR_VERSION,
            "attempt_id": attempt.id,
            "short_url": link_result.short_url,
            "used_fallback": used_fallback,
            "reconciled": reconciled,
            "response": redact_sensitive_data(link_result.raw_response),
        }, separators=(",", ":")),
    )
    db.add(link)

    # 2. Audit event: PAYMENT_LINK_CREATED (dispatched)
    audit_dispatched = AuditEvent(
        event_type="recovery.payment_link.created",
        actor_type="RECOVERY_EXECUTOR",
        actor_id=f"{link_result.provider}:{EXECUTOR_VERSION}",
        entity_type="RecoveryAttempt",
        entity_id=str(attempt.id),
        correlation_id=correlation_id,
        result="EXECUTED",
        metadata_json={
            "provider": provider,
            "execution_strategy": final_strategy,
            "original_strategy": strategy_name,
            "adapter": link_result.provider,
            "operation": operation,
            "opportunity_id": opportunity_id,
            "recovery_attempt_id": attempt.id,
            "attempt_number": attempt_number,
            "correlation_id": correlation_id,
            "policy_decision": policy.result,
            "policy_version": policy.policy_version,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "duration_ms": duration_ms,
            "outcome": "EXECUTED",
            "retryable": False,
            "used_fallback": used_fallback,
            "reconciled": reconciled,
            "external_reference": link_result.payment_link_id,
            "payment_link_id": link_result.payment_link_id,
            "reference_id": link_result.reference_id,
            "short_url": link_result.short_url,
            "amount_minor": opportunity.amount_at_risk_minor,
            "currency": opportunity.currency,
            **(redact_sensitive_data(link_result.metadata or {})),
        },
        outcome_snapshot={
            "status": link_result.status,
            "payment_link_id": link_result.payment_link_id,
            "short_url": link_result.short_url,
            "execution_strategy": final_strategy,
            "used_fallback": used_fallback,
        },
    )
    db.add(audit_dispatched)

    # 3. Audit event: RECOVERY_VERIFICATION_PENDING (awaiting payment)
    audit_pending = AuditEvent(
        event_type="recovery.verification.pending",
        actor_type="RECOVERY_EXECUTOR",
        actor_id=f"{link_result.provider}:{EXECUTOR_VERSION}",
        entity_type="RecoveryAttempt",
        entity_id=str(attempt.id),
        correlation_id=correlation_id,
        result="PENDING",
        metadata_json={
            "provider": provider,
            "execution_strategy": final_strategy,
            "operation": operation,
            "opportunity_id": opportunity_id,
            "recovery_attempt_id": attempt.id,
            "attempt_number": attempt_number,
            "correlation_id": correlation_id,
            "external_reference": link_result.payment_link_id,
        },
        outcome_snapshot={
            "status": "AWAITING_PAYMENT",
            "payment_link_id": link_result.payment_link_id,
        },
    )
    db.add(audit_pending)

    db.commit()
    db.refresh(attempt)
    return attempt
