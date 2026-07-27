from __future__ import annotations

from dataclasses import dataclass

from realty_radar.domain.loan.entities import ApplicantProfile


CAPITAL_SIDO_CODES = frozenset({11, 28, 41})
CAPITAL_ADDRESS_KEYWORDS = ("서울", "경기", "인천")


def is_capital_candidate(sido_code: int, address: str | None) -> bool:
    if sido_code in CAPITAL_SIDO_CODES or not address:
        return True
    return any(keyword in address for keyword in CAPITAL_ADDRESS_KEYWORDS)


@dataclass(frozen=True, slots=True)
class LoanCandidateBranch:
    trade_types: tuple[int, ...]
    capital_max_price: int
    non_capital_max_price: int
    max_exclusive_area_x100: int | None = None

    def matches(
        self,
        *,
        trade_type: int,
        primary_price: int,
        exclusive_area_x100: int,
        sido_code: int,
        address: str | None = None,
    ) -> bool:
        if trade_type not in self.trade_types or primary_price <= 0:
            return False
        max_price = self.capital_max_price if is_capital_candidate(sido_code, address) else self.non_capital_max_price
        if primary_price > max_price:
            return False
        if self.max_exclusive_area_x100 is not None:
            return 0 < exclusive_area_x100 <= self.max_exclusive_area_x100
        return True


@dataclass(frozen=True, slots=True)
class LoanCandidatePlan:
    branches: tuple[LoanCandidateBranch, ...]

    @classmethod
    def for_applicant(cls, applicant: ApplicantProfile | None) -> "LoanCandidatePlan":
        if applicant is None:
            return cls(
                branches=(
                    LoanCandidateBranch((1,), 900_000_000, 900_000_000),
                    LoanCandidateBranch((2, 3, 4), 300_000_000, 200_000_000, 8500),
                )
            )

        sale_limits: list[tuple[int, int | None]] = []
        has_multiple_children = applicant.child_count >= 2

        didimdol_income_limit = 60_000_000
        if applicant.is_newlywed:
            didimdol_income_limit = 85_000_000
        elif applicant.is_first_home_buyer or has_multiple_children:
            didimdol_income_limit = 70_000_000
        if applicant.is_homeless and applicant.annual_income <= didimdol_income_limit:
            didimdol_price_limit = (
                600_000_000
                if applicant.is_newlywed or has_multiple_children
                else 500_000_000
            )
            sale_limits.append((didimdol_price_limit, 8500))

        bogumjari_income_limit = 70_000_000
        if has_multiple_children:
            bogumjari_income_limit = 100_000_000
        elif applicant.child_count == 1:
            bogumjari_income_limit = 90_000_000
        elif applicant.is_newlywed:
            bogumjari_income_limit = 85_000_000
        if applicant.annual_income <= bogumjari_income_limit:
            sale_limits.append((600_000_000, None))

        if applicant.has_newborn and applicant.annual_income <= 200_000_000:
            sale_limits.append((900_000_000, None))

        branches: list[LoanCandidateBranch] = []
        if sale_limits:
            branches.append(
                LoanCandidateBranch(
                    trade_types=(1,),
                    capital_max_price=max(limit for limit, _ in sale_limits),
                    non_capital_max_price=max(limit for limit, _ in sale_limits),
                    max_exclusive_area_x100=(
                        max(area for _, area in sale_limits if area is not None)
                        if all(area is not None for _, area in sale_limits)
                        else None
                    ),
                )
            )

        special_rental_limit = applicant.is_newlywed or has_multiple_children
        rental_income_limit = 75_000_000 if special_rental_limit else 50_000_000
        if applicant.annual_income <= rental_income_limit:
            branches.append(
                LoanCandidateBranch(
                    trade_types=(2, 3, 4),
                    capital_max_price=500_000_000 if special_rental_limit else 300_000_000,
                    non_capital_max_price=400_000_000 if special_rental_limit else 200_000_000,
                    max_exclusive_area_x100=8500,
                )
            )

        return cls(branches=tuple(branches))

    def matches(
        self,
        *,
        trade_type: int,
        primary_price: int,
        exclusive_area_x100: int,
        sido_code: int,
        address: str | None = None,
    ) -> bool:
        return any(
            branch.matches(
                trade_type=trade_type,
                primary_price=primary_price,
                exclusive_area_x100=exclusive_area_x100,
                sido_code=sido_code,
                address=address,
            )
            for branch in self.branches
        )
