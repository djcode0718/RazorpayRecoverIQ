from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr


DIAGNOSIS_SCHEMA_VERSION = "v1"


class DiagnosisEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    signal: StrictStr = Field(min_length=1, max_length=64)
    observation: StrictStr = Field(min_length=1, max_length=256)
    impact: Literal["LOW", "MEDIUM", "HIGH"]


class StructuredDiagnosis(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    diagnosis: StrictStr = Field(min_length=20, max_length=1200)
    failure_category: StrictStr = Field(min_length=1, max_length=64)
    recommended_action: Literal[
        "CREATE_PAYMENT_LINK",
        "RETRY",
        "DELAYED_RETRY",
        "RECOVERY_PROMPT",
        "ALTERNATE_PAYMENT_PATH",
        "ESCALATE",
        "NO_ACTION",
    ]
    recovery_probability: int = Field(ge=0, le=100)
    confidence: int = Field(ge=0, le=100)
    reason: StrictStr = Field(min_length=10, max_length=400)
    uncertainties: list[StrictStr] = Field(default_factory=list, max_length=6)
    evidence: list[DiagnosisEvidence] = Field(min_length=1, max_length=10)
    provider_metadata: dict[str, StrictStr] = Field(default_factory=dict)
