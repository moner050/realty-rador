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
    mysql_database: str = Field(default="realty_radar", validation_alias="MYSQL_DATABASE")
    mysql_user: str = Field(default="realty_app", validation_alias="MYSQL_USER")
    mysql_password: str = Field(default="realty_secret_pass", validation_alias="MYSQL_PASSWORD")

    data_directory: Path = Field(default=Path("./data"), validation_alias="DATA_DIRECTORY")
    auth_directory: Path = Field(default=Path("./data/auth"), validation_alias="AUTH_DIRECTORY")
    snapshot_directory: Path = Field(default=Path("./data/snapshots"), validation_alias="SNAPSHOT_DIRECTORY")
    screenshot_directory: Path = Field(default=Path("./data/screenshots"), validation_alias="SCREENSHOT_DIRECTORY")

    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

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
