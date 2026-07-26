from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from realty_radar.config import settings


def create_db_engine(url: str | None = None) -> Engine:
    """SQLAlchemy 동기 커넥션 풀 엔진 생성 함수 (끊김 방지 설정 강화)."""
    connection_url = url or settings.sqlalchemy_database_url
    connect_args = {}
    if "mysql" in connection_url:
        connect_args = {
            "connect_timeout": 10,
            "read_timeout": 60,
            "write_timeout": 60,
        }

    return create_engine(
        connection_url,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=10,
        max_overflow=20,
        connect_args=connect_args,
        echo=settings.log_level.upper() == "DEBUG",
    )


# 기본 엔진 객체
engine = create_db_engine()
