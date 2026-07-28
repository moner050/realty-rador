from collections.abc import Generator
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from realty_radar.infrastructure.database.engine import engine

# SQLAlchemy SessionFactory 생성
SessionFactory = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

# 하위 호환 별칭
SessionLocal = SessionFactory


def get_db() -> Generator[Session, None, None]:
    """FastAPI 및 비즈니스 로직용 데이터베이스 세션 제너레이터 (웹 세션 락 무한 대기 방지)."""
    db = SessionFactory()
    try:
        if db.bind is not None and db.bind.dialect.name == "mysql":
            try:
                db.execute(text("SET SESSION innodb_lock_wait_timeout = 3"))
            except Exception:
                pass
        yield db
    finally:
        try:
            db.close()
        except Exception:
            pass
