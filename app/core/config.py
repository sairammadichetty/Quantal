from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings, loaded from env vars / .env."""

    APP_NAME: str = "Orbital Copilot Usage API"
    DEBUG: bool = False

    ORBITAL_BASE_URL: str = "https://owpublic.blob.core.windows.net/tech-task"
    # Kept in config so a new billing period (e.g. /messages/2025-Q1) is a
    # deploy change, not a code change.
    ORBITAL_MESSAGES_PATH: str = "/messages/current-period"
    ORBITAL_REPORT_PATH_TEMPLATE: str = "/reports/{report_id}"

    # Per-request HTTP timeout in seconds. Exposed as a setting so ops can tune
    # it without a redeploy if the upstream gets slow.
    ORBITAL_HTTP_TIMEOUT_SECONDS: float = 10.0

    # Normalise path settings so a missing leading slash doesn't silently
    # break URL joining against the base URL.
    @field_validator("ORBITAL_MESSAGES_PATH", "ORBITAL_REPORT_PATH_TEMPLATE")
    @classmethod
    def _ensure_leading_slash(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("path settings must not be empty")
        return value if value.startswith("/") else f"/{value}"

    @field_validator("ORBITAL_REPORT_PATH_TEMPLATE")
    @classmethod
    def _require_report_id_placeholder(cls, value: str) -> str:
        if "{report_id}" not in value:
            raise ValueError(
                "ORBITAL_REPORT_PATH_TEMPLATE must contain a `{report_id}` placeholder"
            )
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=True,
    )


@lru_cache
def get_settings() -> Settings:
    """Return a process-wide cached Settings instance. Avoids re-parsing the .env file on every call"""
    return Settings()


settings = get_settings()
