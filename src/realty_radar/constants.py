from enum import Enum


class TransactionType(str, Enum):
    """거래 유형 enum."""

    SALE = "SALE"  # 매매
    JEONSE = "JEONSE"  # 전세
    MONTHLY_RENT = "MONTHLY_RENT"  # 월세


class ListingStatus(str, Enum):
    """매물 상태 enum."""

    ACTIVE = "ACTIVE"  # 확인됨
    STALE = "STALE"  # 최근 미발견
    REMOVED = "REMOVED"  # 연속 미발견 삭제 추정
    SOLD_OR_CONTRACTED = "SOLD_OR_CONTRACTED"  # 거래 완료
    UNKNOWN = "UNKNOWN"  # 상태 알수없음


class MortgageStatus(str, Enum):
    """융자 상태 enum."""

    EXPLICIT_NONE = "EXPLICIT_NONE"  # 융자 없음 명시
    EXPLICIT_EXISTS = "EXPLICIT_EXISTS"  # 융자 있음 명시
    UNKNOWN = "UNKNOWN"  # 정보 미상


class SortBy(str, Enum):
    """매물 검색 정렬 기준 enum."""

    RECENT = "recent"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"
    AREA_DESC = "area_desc"
    AREA_ASC = "area_asc"
    HOUSEHOLDS_DESC = "households_desc"
    HOUSEHOLDS_ASC = "households_asc"


class CrawlJobStatus(str, Enum):
    """크롤링 작업 상태 enum."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RETRY_WAIT = "RETRY_WAIT"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class CrawlJobType(str, Enum):
    """크롤링 작업 유형 enum."""

    SEARCH = "SEARCH"
    DETAIL = "DETAIL"
    AVAILABILITY_CHECK = "AVAILABILITY_CHECK"


class MatchMethod(str, Enum):
    """단지 매칭 방식 enum."""

    ADDRESS_EXACT = "ADDRESS_EXACT"
    NAME_EXACT = "NAME_EXACT"
    FUZZY = "FUZZY"
    MANUAL = "MANUAL"
