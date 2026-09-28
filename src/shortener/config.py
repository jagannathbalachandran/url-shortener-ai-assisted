"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATABASE_URL = "sqlite:///./shortener.db"
DEFAULT_BASE_URL = "http://localhost:8000"


class Settings(BaseSettings):
    """Runtime settings sourced from environment variables or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = DEFAULT_DATABASE_URL
    base_url: str = DEFAULT_BASE_URL

    @field_validator("base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        """Strip trailing slashes so short links never get a double slash."""
        return value.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide cached Settings instance."""
    return Settings()
