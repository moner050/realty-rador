from datetime import date


class LoanPolicyLoader:
    """시행일자 및 규칙 버전 로더."""

    @staticmethod
    def get_effective_policy_version() -> dict:
        """현재 적용 중인 정부 대출 정책 기준 버전 반환."""
        return {
            "version": "2026.01",
            "effective_date": date(2026, 1, 1),
            "didimdol_max_price": 500_000_000,
            "didimdol_newlywed_max_price": 600_000_000,
            "beotimmok_max_deposit": 300_000_000,
            "beotimmok_newlywed_max_deposit": 400_000_000,
            "max_exclusive_area": 85.0,
        }
