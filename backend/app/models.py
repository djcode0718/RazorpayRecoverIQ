from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _utc_now_naive() -> datetime:
    # Keep existing naive-UTC storage semantics while avoiding deprecated utcnow().
    return datetime.now(UTC).replace(tzinfo=None)


class Merchant(Base):
    __tablename__ = "merchants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    razorpay_account_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, onupdate=_utc_now_naive, nullable=False)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_customer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    segment: Mapped[str | None] = mapped_column(String(64), nullable=True)
    total_payment_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successful_payment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_payment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_success_value: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    average_payment_value: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    historical_recovery_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    historical_recovery_rate: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_successful_payment_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, onupdate=_utc_now_naive, nullable=False)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    razorpay_order_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    raw_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, onupdate=_utc_now_naive, nullable=False)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    razorpay_order_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    captured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_step: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, onupdate=_utc_now_naive, nullable=False)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    razorpay_subscription_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    razorpay_customer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    plan_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    current_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    charge_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paid_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remaining_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    auth_attempts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, onupdate=_utc_now_naive, nullable=False)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("razorpay_event_id", name="uq_webhook_events_razorpay_event_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    razorpay_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    account_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, nullable=False)
    signature_valid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processing_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_payload: Mapped[str] = mapped_column(Text, nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


class WebhookProcessorLedger(Base):
    __tablename__ = "webhook_processor_ledger"
    __table_args__ = (UniqueConstraint("razorpay_event_id", name="uq_processor_ledger_razorpay_event_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    razorpay_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    event_created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    first_received_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, nullable=False)
    last_received_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, nullable=False)
    delivery_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_processing_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


class RevenueOpportunity(Base):
    __tablename__ = "revenue_opportunities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subscription_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount_at_risk_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    failure_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    recovery_probability: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recovery_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expected_recovery_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_intervention_cost_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expected_net_recovery_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recommended_action: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, onupdate=_utc_now_naive, nullable=False)


class RecoveryDecision(Base):
    __tablename__ = "recovery_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    diagnosis: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    recovery_probability: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recommended_action: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_recovery_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expected_net_recovery_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    decision_source: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    schema_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, nullable=False)


class AIAnalysis(Base):
    __tablename__ = "ai_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    decision_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    valid_schema: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    failure_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    diagnosis: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recommended_action: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_output: Mapped[dict] = mapped_column(JSON, nullable=False)
    validation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, nullable=False)


class PolicyEvaluation(Base):
    __tablename__ = "policy_evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    decision_id: Mapped[int] = mapped_column(Integer, nullable=False)
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_codes: Mapped[dict] = mapped_column(JSON, nullable=False)
    evaluated_rules: Mapped[dict] = mapped_column(JSON, nullable=False)
    max_amount_check: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confidence_check: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    retry_limit_check: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    economic_check: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duplicate_check: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    environment_check: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)


class RecoveryAttempt(Base):
    __tablename__ = "recovery_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_evaluation_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, nullable=False)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    external_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    verified_outcome: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recovered_amount_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class RecoveryOutcome(Base):
    __tablename__ = "recovery_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt_id: Mapped[int] = mapped_column(Integer, nullable=False)
    opportunity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    recovered_amount_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    verification_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, nullable=False)


class RecoveryPaymentLink(Base):
    __tablename__ = "recovery_payment_links"
    __table_args__ = (UniqueConstraint("payment_link_reference_id", name="uq_recovery_payment_links_reference_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    recovery_attempt_id: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_link_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payment_link_reference_id: Mapped[str] = mapped_column(String(128), nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    external_response_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, onupdate=_utc_now_naive, nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    result: Mapped[str | None] = mapped_column(String(32), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    input_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    decision_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    policy_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    outcome_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class EvaluationCase(Base):
    __tablename__ = "evaluation_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_version: Mapped[str] = mapped_column(String(32), nullable=False)
    generation_seed: Mapped[int] = mapped_column(Integer, nullable=False)
    case_type: Mapped[str] = mapped_column(String(64), nullable=False)
    customer_features: Mapped[dict] = mapped_column(JSON, nullable=False)
    payment_features: Mapped[dict] = mapped_column(JSON, nullable=False)
    failure_features: Mapped[dict] = mapped_column(JSON, nullable=False)
    history_features: Mapped[dict] = mapped_column(JSON, nullable=False)
    ground_truth_recoverable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ground_truth_action: Mapped[str] = mapped_column(String(64), nullable=False)
    ground_truth_recovered_amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    split: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, nullable=False)


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    evaluation_run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    case_id: Mapped[int] = mapped_column(Integer, nullable=False)
    predicted_recoverable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    predicted_action: Mapped[str] = mapped_column(String(64), nullable=False)
    predicted_probability: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_recoverable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    actual_action: Mapped[str] = mapped_column(String(64), nullable=False)
    correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    false_positive: Mapped[bool] = mapped_column(Boolean, nullable=False)
    false_negative: Mapped[bool] = mapped_column(Boolean, nullable=False)
    recovered_amount_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    intervention_cost_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    net_recovered_amount_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, nullable=False)
