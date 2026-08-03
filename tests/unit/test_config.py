from realty_radar.config import Settings


def test_settings_default_values():
    """기본 설정값 및 SQLAlchemy 연결 문자열 생성 테스트."""
    custom_settings = Settings(
        APP_ENV="local",
        MYSQL_HOST="localhost",
        MYSQL_PORT=3306,
        MYSQL_USER="test_user",
        MYSQL_PASSWORD="test_password",
        MYSQL_DATABASE="test_db",
    )
    assert custom_settings.app_env == "local"
    assert custom_settings.sqlalchemy_database_url == "mysql+pymysql://test_user:test_password@localhost:3306/test_db?charset=utf8mb4"


def test_settings_reads_naver_map_credentials_from_environment(monkeypatch):
    monkeypatch.setenv("NAVER_MAP_CLIENT_ID", "public-key")
    monkeypatch.setenv("NAVER_MAP_CLIENT_SECRET", "server-secret")

    configured = Settings(_env_file=None)

    assert configured.naver_map_client_id == "public-key"
    assert configured.naver_map_client_secret == "server-secret"
