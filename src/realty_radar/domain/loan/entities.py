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
class PromissoryNoteEntry:
    """차용증 작성 대상별 이름 및 가능 금액 DTO."""

    name: str = ""
    amount: int = 0


@dataclass
class ApplicantProfile:
    """사용자 신청 자격 조건 프로필 DTO."""

    is_homeless: bool = True  # 무주택 여부
    annual_income: int = 60_000_000  # 개인 또는 부부합산 연소득 (원)
    net_assets: int = 300_000_000  # 순자산 (원)
    is_newlywed: bool = False  # 신혼부부 여부 (혼인 7년 이내)
    is_first_home_buyer: bool = False  # 생애최초 주택구입 여부
    child_count: int = 0  # 미성년 자녀 수
    has_newborn: bool = False  # 2년 이내 출산(신생아) 여부
    use_promissory_note: bool = False  # 차용증 작성 활용 여부
    promissory_note_person_count: int = 0  # 하위 호환 인원 수
    promissory_note_amount: int = 0  # 하위 호환 단일 지정 금액 (원)
    promissory_notes: list[PromissoryNoteEntry] = field(default_factory=list)  # 동적 차용증 작성인 항목 리스트

    @property
    def promissory_note_total(self) -> int:
        """등록된 동적 차용증 항목들의 가능 금액 총합."""
        if not self.use_promissory_note:
            return 0
        if self.promissory_notes:
            return sum(e.amount for e in self.promissory_notes)
        if self.promissory_note_amount > 0:
            return self.promissory_note_amount
        return self.promissory_note_person_count * 217_000_000

    @property
    def total_capital(self) -> int:
        """순자산 및 차용증 작성 자금을 합산한 총 가용 자본금."""
        return self.net_assets + self.promissory_note_total


@dataclass
class LoanEvaluationResult:
    """대출 평가 결과 DTO."""

    product_code: str
    product_name: str
    status: LoanEligibilityStatus
    max_loan_amount: int | None = None
    reason: str | None = None
    interest_rate: float | None = None  # 예상 연 이자율 (%)
    estimated_monthly_interest: int | None = None  # 월 예상 이자 (원)

    @property
    def is_eligible(self) -> bool:
        """적격 여부 간편 판단."""
        return self.status in (LoanEligibilityStatus.ELIGIBLE, LoanEligibilityStatus.PROPERTY_ELIGIBLE)

    @property
    def loan_type_name(self) -> str:
        """대출 상품 한글 약칭."""
        names = {
            "DIDIMDOL": "디딤돌",
            "BOGUMJARI": "보금자리론",
            "NEONATAL_PURCHASE": "신생아특례",
            "BEOTIMMOK": "버팀목",
        }
        return names.get(self.product_code, self.product_name)
