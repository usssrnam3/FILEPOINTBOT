from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = Field(alias="BOT_TOKEN")
    database_url: str = Field(alias="DATABASE_URL")
    alembic_database_url: str = Field(alias="ALEMBIC_DATABASE_URL")
    redis_url: str = Field(alias="REDIS_URL")
    admin_ids: set[int] = Field(default_factory=set, alias="ADMIN_IDS")
    storage_dir: Path = Field(default=Path("storage/files"), alias="STORAGE_DIR")
    app_env: str = Field(default="dev", alias="APP_ENV")
    payment_provider: str = Field(default="demo", alias="PAYMENT_PROVIDER")
    app_name: str = Field(default="FilePoint", alias="APP_NAME")

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: str | int | list[int] | set[int] | tuple[int, ...] | None) -> set[int]:
        if value is None:
            return set()
        if isinstance(value, int):
            return {value}
        if isinstance(value, set):
            return value
        if isinstance(value, tuple):
            return {int(item) for item in value}
        if isinstance(value, list):
            return {int(item) for item in value}
        return {int(item.strip()) for item in value.split(",") if item.strip()}

    def is_admin(self, telegram_id: int) -> bool:
        return telegram_id in self.admin_ids


@lru_cache
def get_settings() -> Settings:
    return Settings()
