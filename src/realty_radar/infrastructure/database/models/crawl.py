from datetime import datetime
from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from realty_radar.infrastructure.database.models.base import Base


class CrawlSource(Base):
    """크롤링 대상 출처 사이트 정보 테이블."""

    __tablename__ = "crawl_source"
    __table_args__ = (
        {"comment": "크롤링 대상 출처 사이트 관리 테이블"},
    )

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True, comment="출처 일련번호 (PK)")
    source_code = Column(String(50), unique=True, nullable=False, comment="출처 고유 코드 (SITE_A, SITE_B 등)")
    source_name = Column(String(100), nullable=False, comment="출처 사이트 이름 (예: 네이버부동산, 아실)")
    base_url = Column(String(255), nullable=False, comment="출처 사이트 기본 접속 URL")

    rate_limit_ms = Column(Integer, default=3000, nullable=False, comment="수집 요청 제한 간격 (밀리초 단위)")
    is_active = Column(Boolean, default=True, nullable=False, comment="수집 활성화 여부 (True: 사용, False: 중지)")

    created_at = Column(DateTime, default=datetime.now, nullable=False, comment="등록 일시")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment="수정 일시")

    # 관계 정의
    schedules = relationship("CrawlSchedule", back_populates="source", cascade="all, delete-orphan")
    jobs = relationship("CrawlJob", back_populates="source", cascade="all, delete-orphan")

    def __init__(self, **kwargs):
        if "code" in kwargs:
            kwargs["source_code"] = kwargs.pop("code")
        if "name" in kwargs:
            kwargs["source_name"] = kwargs.pop("name")
        if "adapter_name" in kwargs:
            kwargs.pop("adapter_name")
        super().__init__(**kwargs)

    @property
    def code(self) -> str:
        return self.source_code

    @code.setter
    def code(self, value: str):
        self.source_code = value

    @property
    def name(self) -> str:
        return self.source_name

    @name.setter
    def name(self, value: str):
        self.source_name = value


class CrawlSchedule(Base):
    """크롤링 주도 스케줄러 등록 테이블."""

    __tablename__ = "crawl_schedule"
    __table_args__ = (
        Index("idx_schedule_next_run", "is_enabled", "next_run_at"),
        {"comment": "크롤링 자동 주도 스케줄 테이블"},
    )

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True, comment="스케줄 일련번호 (PK)")
    source_id = Column(BigInteger().with_variant(Integer, "sqlite"), ForeignKey("crawl_source.id", ondelete="CASCADE"), nullable=False, comment="연결된 출처 사이트 ID (FK)")

    target_region = Column(String(100), nullable=False, comment="수집 대상 지역/키워드 (예: 여의도동, 서울전체)")
    cron_expression = Column(String(50), nullable=False, comment="크론 주기 표현식 (예: 0 */6 * * *)")
    is_enabled = Column(Boolean, default=True, nullable=False, comment="스케줄 활성화 여부")

    last_run_at = Column(DateTime, nullable=True, comment="최근 실행 일시")
    next_run_at = Column(DateTime, nullable=True, comment="다음 실행 예정 일시")

    created_at = Column(DateTime, default=datetime.now, nullable=False, comment="스케줄 등록 일시")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment="스케줄 수정 일시")

    # 관계 정의
    source = relationship("CrawlSource", back_populates="schedules")


class CrawlJob(Base):
    """크롤링 비동기 작업 큐 상태 관리 테이블."""

    __tablename__ = "crawl_job"
    __table_args__ = (
        Index("idx_job_polling", "status", "priority", "created_at"),
        Index("idx_job_source_status", "source_id", "status"),
        {"comment": "크롤링 비동기 작업 큐 테이블"},
    )

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True, comment="작업 일련번호 (PK)")
    source_id = Column(BigInteger().with_variant(Integer, "sqlite"), ForeignKey("crawl_source.id", ondelete="CASCADE"), nullable=False, comment="연결된 출처 사이트 ID (FK)")
    schedule_id = Column(BigInteger().with_variant(Integer, "sqlite"), ForeignKey("crawl_schedule.id", ondelete="SET NULL"), nullable=True, comment="연결된 스케줄 ID (FK)")

    job_type = Column(String(30), nullable=False, comment="작업 유형 (SEARCH, DETAIL, AVAILABILITY_CHECK)")
    target_region = Column(String(100), nullable=True, comment="수집 대상 지역명")
    target_url = Column(Text, nullable=True, comment="수집 대상 상세 URL")

    status = Column(String(30), default="PENDING", nullable=False, comment="작업 상태 (PENDING, RUNNING, SUCCESS, FAILED 등)")
    priority = Column(Integer, default=10, nullable=False, comment="우선순위 (낮을수록 먼저 처리)")
    retry_count = Column(Integer, default=0, nullable=False, comment="재시도 누적 횟수")
    max_retries = Column(Integer, default=3, nullable=False, comment="최대 재시도 가능 횟수")
    next_retry_at = Column(DateTime, nullable=True, comment="다음 재시도 예정 일시")

    worker_id = Column(String(100), nullable=True, comment="선점한 Worker 프로세스 식별자")
    error_type = Column(String(100), nullable=True, comment="오류 발생 시 예외 클래스명")
    error_message = Column(Text, nullable=True, comment="오류 발생 상세 메시지")

    started_at = Column(DateTime, nullable=True, comment="작업 처리 시작 일시")
    finished_at = Column(DateTime, nullable=True, comment="작업 완료/실패 일시")

    created_at = Column(DateTime, default=datetime.now, nullable=False, comment="작업 생성 일시")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment="수정 일시")

    # 관계 정의
    source = relationship("CrawlSource", back_populates="jobs")

    def __init__(self, **kwargs):
        if "request_json" in kwargs:
            req_data = kwargs.pop("request_json")
            if isinstance(req_data, dict) and "region_name" in req_data:
                kwargs["target_region"] = req_data["region_name"]
        if "job_status" in kwargs:
            val = kwargs.pop("job_status")
            kwargs["status"] = val.value if hasattr(val, "value") else str(val)
        if "queued_at" in kwargs:
            kwargs["created_at"] = kwargs.pop("queued_at")

        super().__init__(**kwargs)

    @property
    def job_status(self):
        return self.status

    @job_status.setter
    def job_status(self, val):
        self.status = val.value if hasattr(val, "value") else str(val)

    @property
    def attempt_count(self):
        return self.retry_count

    @attempt_count.setter
    def attempt_count(self, val):
        self.retry_count = val

    @property
    def queued_at(self):
        return self.created_at

    @property
    def completed_at(self):
        return self.finished_at

    @completed_at.setter
    def completed_at(self, val):
        self.finished_at = val

    @property
    def request_json(self):
        return {"region_name": self.target_region, "url": self.target_url}
