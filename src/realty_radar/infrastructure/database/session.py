from collections.abc import Generator
from sqlalchemy.orm import Session, sessionmaker

from realty_radar.infrastructure.database.engine import engine

# SQLAlchemy SessionFactory 생성
SessionFactory = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 및 비즈니스 로직용 데이터베이스 세션 제너레이터."""
    db = SessionFactory()
    try:
        yield db
    finally:
        try:
            db.close()
        except Exception:
            pass
