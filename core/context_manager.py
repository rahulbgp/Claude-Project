import time
from dataclasses import dataclass, field
from typing import Optional
from core.models import EligibilityResult, LoanDecision


@dataclass
class RequestContext:
    trace_id: str
    applicant_data: dict
    start_time: float = field(default_factory=time.time)
    session_id: str = "default"
    eligibility: Optional[EligibilityResult] = None
    risk_band: Optional[str] = None
    decision: Optional[LoanDecision] = None
    bias_flags: list = field(default_factory=list)
    plan: list = field(default_factory=list)

    @property
    def elapsed_ms(self) -> int:
        return int((time.time() - self.start_time) * 1000)
