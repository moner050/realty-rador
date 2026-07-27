from dataclasses import dataclass, field
from enum import Enum
from typing import Any


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

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "amount": self.amount}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PromissoryNoteEntry":
        return cls(name=data.get("name", ""), amount=data.get("amount", 0))


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

    def to_dict(self) -> dict[str, Any]:
        """JSON 직렬화용 Dict 변환."""
        return {
            "is_homeless": self.is_homeless,
            "annual_income": self.annual_income,
            "net_assets": self.net_assets,
            "is_newlywed": self.is_newlywed,
            "is_first_home_buyer": self.is_first_home_buyer,
            "child_count": self.child_count,
            "has_newborn": self.has_newborn,
            "use_promissory_note": self.use_promissory_note,
            "promissory_note_person_count": self.promissory_note_person_count,
            "promissory_note_amount": self.promissory_note_amount,
            "promissory_notes": [e.to_dict() for e in self.promissory_notes],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApplicantProfile":
        """Dict 데이터로부터 ApplicantProfile 객체 복원."""
        notes_data = data.get("promissory_notes", [])
        notes = [PromissoryNoteEntry.from_dict(n) for n in notes_data if isinstance(n, dict)]
        return cls(
            is_homeless=data.get("is_homeless", True),
            annual_income=data.get("annual_income", 60_000_000),
            net_assets=data.get("net_assets", 300_000_000),
            is_newlywed=data.get("is_newlywed", False),
            is_first_home_buyer=data.get("is_first_home_buyer", False),
            child_count=data.get("child_count", 0),
            has_newborn=data.get("has_newborn", False),
            use_promissory_note=data.get("use_promissory_note", False),
            promissory_note_person_count=data.get("promissory_note_person_count", 0),
            promissory_note_amount=data.get("promissory_note_amount", 0),
            promissory_notes=notes,
        )


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
    calculation_criteria: list[tuple[str, str]] = field(default_factory=list)

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
