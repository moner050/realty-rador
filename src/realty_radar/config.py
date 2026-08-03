import os
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """애플리케이션 환경 변수 및 전역 설정 관리 클래스."""

    app_env: str = Field(default="local", validation_alias="APP_ENV")
    app_host: str = Field(default="127.0.0.1", validation_alias="APP_HOST")
    app_port: int = Field(default=8000, validation_alias="APP_PORT")

    mysql_host: str = Field(default="127.0.0.1", validation_alias="MYSQL_HOST")
    mysql_port: int = Field(default=3306, validation_alias="MYSQL_PORT")
    mysql_database: str = Field(default="realty_radar_v2", validation_alias="MYSQL_DATABASE")
    mysql_user: str = Field(default="realty_app", validation_alias="MYSQL_USER")
    mysql_password: str = Field(default="realty_secret_pass", validation_alias="MYSQL_PASSWORD")

    redis_host: str = Field(default="127.0.0.1", validation_alias="REDIS_HOST")
    redis_port: int = Field(default=6379, validation_alias="REDIS_PORT")
    redis_password: str | None = Field(default=None, validation_alias="REDIS_PASSWORD")
    redis_db: int = Field(default=0, validation_alias="REDIS_DB")

    data_directory: Path = Field(default=Path("./data"), validation_alias="DATA_DIRECTORY")
    auth_directory: Path = Field(default=Path("./data/auth"), validation_alias="AUTH_DIRECTORY")
    snapshot_directory: Path = Field(default=Path("./data/snapshots"), validation_alias="SNAPSHOT_DIRECTORY")
    screenshot_directory: Path = Field(default=Path("./data/screenshots"), validation_alias="SCREENSHOT_DIRECTORY")

    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    public_data_api_key: str | None = Field(default=None, validation_alias="PUBLIC_DATA_API_KEY")
    naver_map_client_id: str | None = Field(default=None, validation_alias="NAVER_MAP_CLIENT_ID")
    naver_map_client_secret: str | None = Field(default=None, validation_alias="NAVER_MAP_CLIENT_SECRET")

    admin_username: str = Field(default="admin", validation_alias="ADMIN_USERNAME")
    admin_password: str = Field(default="admin1234", validation_alias="ADMIN_PASSWORD")
    secret_key: str = Field(default="realty-radar-secret-key-2026", validation_alias="SECRET_KEY")

    google_client_id: str | None = Field(default=None, validation_alias="GOOGLE_CLIENT_ID")
    google_client_secret: str | None = Field(default=None, validation_alias="GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str = Field(default="http://localhost:8000/auth/google/callback", validation_alias="GOOGLE_REDIRECT_URI")


    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def sqlalchemy_database_url(self) -> str:
        """PyMySQL 기반 SQLAlchemy 연결 문자열 생성."""
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
        )


# 전역 싱글톤 설정 객체 생성
settings = Settings()
