from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Payment, RecoveryAttempt, RecoveryOutcome, RecoveryPaymentLink, RevenueOpportunity
from .state_machine import can_transition_recovery


def _utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def verify_recovery_attempt_outcome(db: Session, *, attempt_id: int) -> RecoveryAttempt | None:
    attempt = db.execute(select(RecoveryAttempt).where(RecoveryAttempt.id == attempt_id)).scalar_one_or_none()
    if attempt is None:
        return None

    if attempt.verified_outcome in {"VERIFIED_SUCCESS", "VERIFIED_FAILURE"}:
        return attempt

    opportunity = db.execute(
        select(RevenueOpportunity).where(RevenueOpportunity.id == attempt.opportunity_id)
    ).scalar_one_or_none()
    payment = None
    if opportunity is not None and opportunity.payment_id is not None:
        payment = db.execute(select(Payment).where(Payment.id == opportunity.payment_id)).scalar_one_or_none()

    if payment is None:
        attempt.verified_outcome = "UNVERIFIED"
        attempt.status = "VERIFICATION_BLOCKED"
        attempt.recovered_amount_minor = 0
        attempt.completed_at = _utc_now_naive()
        db.add(
            RecoveryOutcome(
                attempt_id=attempt.id,
                opportunity_id=attempt.opportunity_id,
                payment_id=None,
                status="UNVERIFIED",
                recovered_amount_minor=0,
                verification_notes="payment_record_missing",
            )
        )
        db.commit()
        db.refresh(attempt)
        return attempt

    if payment.status == "CAPTURED":
        attempt.verified_outcome = "VERIFIED_SUCCESS"
        attempt.status = "VERIFIED"
        attempt.recovered_amount_minor = min(attempt.amount_minor, payment.amount_minor)
        if opportunity is not None:
            if can_transition_recovery(opportunity.status, "PAYMENT_SUCCESSFUL"):
                opportunity.status = "PAYMENT_SUCCESSFUL"
            if can_transition_recovery(opportunity.status, "VERIFIED_RECOVERED"):
                opportunity.status = "VERIFIED_RECOVERED"
    elif payment.status == "FAILED":
        attempt.verified_outcome = "VERIFIED_FAILURE"
        attempt.status = "VERIFIED"
        attempt.recovered_amount_minor = 0
        if opportunity is not None:
            if can_transition_recovery(opportunity.status, "PAYMENT_FAILED"):
                opportunity.status = "PAYMENT_FAILED"
            if can_transition_recovery(opportunity.status, "RECOVERY_FAILED"):
                opportunity.status = "RECOVERY_FAILED"
    else:
        attempt.verified_outcome = "VERIFICATION_PENDING"
        attempt.status = "PENDING_VERIFICATION"
        attempt.recovered_amount_minor = 0
        if opportunity is not None and can_transition_recovery(opportunity.status, "PAYMENT_PENDING"):
            opportunity.status = "PAYMENT_PENDING"

    attempt.completed_at = _utc_now_naive()
    db.add(
        RecoveryOutcome(
            attempt_id=attempt.id,
            opportunity_id=attempt.opportunity_id,
            payment_id=payment.id,
            status=attempt.verified_outcome,
            recovered_amount_minor=attempt.recovered_amount_minor,
            verification_notes=f"payment_status={payment.status}",
        )
    )
    db.commit()
    db.refresh(attempt)
    return attempt


def verify_outcomes_for_payment(db: Session, *, payment_id: int) -> list[RecoveryAttempt]:
    opportunities = db.execute(
        select(RevenueOpportunity).where(RevenueOpportunity.payment_id == payment_id)
    ).scalars().all()
    if not opportunities:
        return []

    verified_attempts: list[RecoveryAttempt] = []
    for opportunity in opportunities:
        attempts = db.execute(
            select(RecoveryAttempt).where(RecoveryAttempt.opportunity_id == opportunity.id)
        ).scalars().all()
        for attempt in attempts:
            updated = verify_recovery_attempt_outcome(db, attempt_id=attempt.id)
            if updated is not None:
                verified_attempts.append(updated)
    return verified_attempts


def verify_outcomes_for_payment_link(
    db: Session,
    *,
    payment_link_id: str | None = None,
    reference_id: str | None = None,
    opportunity_id: int | None = None,
    is_success: bool = True,
    amount_minor: int | None = None,
    payment_id: int | None = None,
) -> list[RecoveryAttempt]:
    query = select(RecoveryPaymentLink)
    if payment_link_id:
        query = query.where(RecoveryPaymentLink.payment_link_id == payment_link_id)
    elif reference_id:
        query = query.where(
            (RecoveryPaymentLink.payment_link_reference_id == reference_id)
            | (RecoveryPaymentLink.payment_link_reference_id.startswith(reference_id))
        )
    elif opportunity_id:
        query = query.where(RecoveryPaymentLink.opportunity_id == opportunity_id)
    else:
        return []

    links = db.execute(query).scalars().all()
    verified_attempts: list[RecoveryAttempt] = []
    for link in links:
        link.status = "PAID" if is_success else "FAILED"
        if link.recovery_attempt_id:
            attempt = db.execute(
                select(RecoveryAttempt).where(RecoveryAttempt.id == link.recovery_attempt_id)
            ).scalar_one_or_none()
            if attempt:
                if is_success:
                    attempt.verified_outcome = "VERIFIED_SUCCESS"
                    attempt.status = "VERIFIED"
                    attempt.recovered_amount_minor = amount_minor or attempt.amount_minor
                    attempt.completed_at = _utc_now_naive()
                    opportunity = db.execute(
                        select(RevenueOpportunity).where(RevenueOpportunity.id == attempt.opportunity_id)
                    ).scalar_one_or_none()
                    if opportunity:
                        if can_transition_recovery(opportunity.status, "PAYMENT_SUCCESSFUL"):
                            opportunity.status = "PAYMENT_SUCCESSFUL"
                        if can_transition_recovery(opportunity.status, "VERIFIED_RECOVERED"):
                            opportunity.status = "VERIFIED_RECOVERED"
                    db.add(
                        RecoveryOutcome(
                            attempt_id=attempt.id,
                            opportunity_id=attempt.opportunity_id,
                            payment_id=payment_id,
                            status="VERIFIED_SUCCESS",
                            recovered_amount_minor=attempt.recovered_amount_minor,
                            verification_notes="payment_link_paid",
                        )
                    )
                else:
                    attempt.verified_outcome = "VERIFIED_FAILURE"
                    attempt.status = "VERIFIED"
                    attempt.recovered_amount_minor = 0
                    attempt.completed_at = _utc_now_naive()
                    opportunity = db.execute(
                        select(RevenueOpportunity).where(RevenueOpportunity.id == attempt.opportunity_id)
                    ).scalar_one_or_none()
                    if opportunity:
                        if can_transition_recovery(opportunity.status, "PAYMENT_FAILED"):
                            opportunity.status = "PAYMENT_FAILED"
                        if can_transition_recovery(opportunity.status, "RECOVERY_FAILED"):
                            opportunity.status = "RECOVERY_FAILED"
                    db.add(
                        RecoveryOutcome(
                            attempt_id=attempt.id,
                            opportunity_id=attempt.opportunity_id,
                            payment_id=payment_id,
                            status="VERIFIED_FAILURE",
                            recovered_amount_minor=0,
                            verification_notes="payment_link_failed",
                        )
                    )
                db.commit()
                db.refresh(attempt)
                verified_attempts.append(attempt)
    return verified_attempts
