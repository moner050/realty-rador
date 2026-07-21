from dataclasses import dataclass, field
from enum import Enum


class LoanEligibilityStatus(str, Enum):
    """대출 적격성 상태 enum."""

    ELIGIBLE = "ELIGIBLE"  # 매물 및 개인 조건 모두 충족
    PROPERTY_ELIGIBLE = "PROPERTY_ELIGIBLE"  # 매물 조건은 충족, 개인 조건 확인 필요
    CONDITIONAL = "CONDITIONAL"  # 일부 정보 부족
    INELIGIBLE = "INELIGIBLE"  # 조건 초과 불적격
    UNKNOWN = "UNKNOWN"  # 판정 불가


@dataclass
class ApplicantProfile:
    """사용자 신청 자격 조건 프로필 DTO."""

    is_homeless: bool = True  # 무주택 여부
    annual_income: int = 60_000_000  # 부부합산 연소득 (원)
    net_assets: int = 300_000_000  # 순자산 (원)
    is_newlywed: bool = False  # 신혼부부 여부 (혼인 7년 이내)
    is_first_home_buyer: bool = False  # 생애최초 주택구입 여부
    child_count: int = 0  # 미성년 자녀 수
    has_newborn: bool = False  # 2년 이내 출산(신생아) 여부


@dataclass
class LoanEvaluationResult:
    """대출 평가 결과 DTO."""

    product_code: str
    product_name: str
    status: LoanEligibilityStatus
    max_loan_amount: int | None = None
    reason: str | None = None
