from enum import StrEnum


class PaymentAttemptStatus(StrEnum):
    CREATING = "creating"
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXPIRED = "expired"
    REQUIRES_REFUND = "requires_refund"
