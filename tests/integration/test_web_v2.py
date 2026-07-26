from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.infrastructure.database.models import Base
from realty_radar.infrastructure.database.session import get_db
from realty_radar.web.main import app


def test_home_renders_v2_cursor_search_without_a_database_count_query():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).get("/?sigungu_code=11500&sort_by=price_asc")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "cursor 조회" in response.text
