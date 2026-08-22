from enum import StrEnum


class PaymentStatus(StrEnum):
    CREATED = "CREATED"
    PENDING = "PENDING"
    FAILED = "FAILED"
    RECOVERY_ELIGIBLE = "RECOVERY_ELIGIBLE"
    RECOVERY_PENDING = "RECOVERY_PENDING"
    CAPTURED = "CAPTURED"


_ALLOWED_PAYMENT_TRANSITIONS: dict[PaymentStatus, set[PaymentStatus]] = {
    PaymentStatus.CREATED: {PaymentStatus.PENDING, PaymentStatus.FAILED, PaymentStatus.CAPTURED},
    PaymentStatus.PENDING: {PaymentStatus.FAILED, PaymentStatus.CAPTURED},
    PaymentStatus.FAILED: {PaymentStatus.RECOVERY_ELIGIBLE, PaymentStatus.CAPTURED},
    PaymentStatus.RECOVERY_ELIGIBLE: {PaymentStatus.RECOVERY_PENDING, PaymentStatus.CAPTURED},
    PaymentStatus.RECOVERY_PENDING: {PaymentStatus.CAPTURED, PaymentStatus.FAILED},
    PaymentStatus.CAPTURED: set(),
}


def can_transition_payment(current: str, target: str) -> bool:
    if current == target:
        return True
    try:
        current_status = PaymentStatus(current)
        target_status = PaymentStatus(target)
    except ValueError:
        return False
    return target_status in _ALLOWED_PAYMENT_TRANSITIONS[current_status]


class RecoveryState(StrEnum):
    IDENTIFIED = "IDENTIFIED"
    ANALYZED = "ANALYZED"
    RECOMMENDED = "RECOMMENDED"
    POLICY_ALLOWED = "POLICY_ALLOWED"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    ESCALATED = "ESCALATED"
    PAYMENT_LINK_CREATED = "PAYMENT_LINK_CREATED"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    PAYMENT_SUCCESSFUL = "PAYMENT_SUCCESSFUL"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    VERIFIED_RECOVERED = "VERIFIED_RECOVERED"
    RECOVERY_FAILED = "RECOVERY_FAILED"


_ALLOWED_RECOVERY_TRANSITIONS: dict[RecoveryState, set[RecoveryState]] = {
    RecoveryState.IDENTIFIED: {RecoveryState.ANALYZED, RecoveryState.ESCALATED},
    RecoveryState.ANALYZED: {RecoveryState.RECOMMENDED, RecoveryState.ESCALATED},
    RecoveryState.RECOMMENDED: {
        RecoveryState.POLICY_ALLOWED,
        RecoveryState.POLICY_BLOCKED,
        RecoveryState.ESCALATED,
    },
    RecoveryState.POLICY_ALLOWED: {RecoveryState.PAYMENT_LINK_CREATED, RecoveryState.PAYMENT_PENDING},
    RecoveryState.POLICY_BLOCKED: set(),
    RecoveryState.ESCALATED: set(),
    RecoveryState.PAYMENT_LINK_CREATED: {
        RecoveryState.PAYMENT_PENDING,
        RecoveryState.PAYMENT_SUCCESSFUL,
        RecoveryState.PAYMENT_FAILED,
    },
    RecoveryState.PAYMENT_PENDING: {
        RecoveryState.PAYMENT_SUCCESSFUL,
        RecoveryState.PAYMENT_FAILED,
    },
    RecoveryState.PAYMENT_SUCCESSFUL: {RecoveryState.VERIFIED_RECOVERED},
    RecoveryState.PAYMENT_FAILED: {RecoveryState.RECOVERY_FAILED},
    RecoveryState.VERIFIED_RECOVERED: set(),
    RecoveryState.RECOVERY_FAILED: set(),
}


def can_transition_recovery(current: str, target: str) -> bool:
    if current == target:
        return True
    try:
        current_state = RecoveryState(current)
        target_state = RecoveryState(target)
    except ValueError:
        return False
    return target_state in _ALLOWED_RECOVERY_TRANSITIONS[current_state]
