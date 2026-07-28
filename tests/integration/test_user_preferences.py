from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.infrastructure.database.models import Base
from realty_radar.infrastructure.database.models.v2 import UserAccount
from realty_radar.infrastructure.database.session import get_db
from realty_radar.web.auth import SESSION_COOKIE_NAME, create_session_token, hash_password
from realty_radar.web.main import app


@pytest.fixture
def preference_client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    with factory() as session:
        session.add(UserAccount(username="favorite-user", password_hash=hash_password("secret123")))
        session.commit()

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE_NAME, create_session_token("favorite-user"))
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


def test_authenticated_preference_persists_favorites_across_requests(preference_client: TestClient):
    favorites = {
        "listings": [{"article_id": 101, "complex_name": "게스트 단지"}],
        "complexes": [{"complex_id": 202, "complex_name": "보관 단지"}],
        "isGroupMode": True,
    }

    saved = preference_client.post("/api/user/preference", json={"favorites": favorites})
    loaded = preference_client.get("/api/user/preference")

    assert saved.status_code == 200
    assert loaded.status_code == 200
    assert loaded.json()["favorites"] == favorites
