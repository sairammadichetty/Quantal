from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the Usage API.

    All external-service URLs and tunables live here so tests and deployments
    can override them via environment variables (or a .env file) without
    touching source. `OrbitalClient` reads these values rather than hard-coding
    them, keeping infrastructure concerns out of the service layer.
    """

    APP_NAME: str = "Orbital Copilot Usage API"
    DEBUG: bool = False

    # Upstream base URL as provided by the task brief. Kept without a trailing
    # slash so callers can join paths predictably (`/messages/current-period`,
    # `/reports/{id}`).
    ORBITAL_BASE_URL: str = "https://owpublic.blob.core.windows.net/tech-task"

    # Path of the messages endpoint. Exposed as a setting because billing
    # periods change (e.g. a future upstream might serve `/messages/2025-Q1`
    # or `/messages/by-period/2025-04`), and we don't want a code change for
    # that. Defaults match the task brief.
    ORBITAL_MESSAGES_PATH: str = "/messages/current-period"

    # URL template for the reports endpoint. Must contain a `{report_id}`
    # placeholder; `OrbitalClient.get_report` fills it in. Templated for
    # symmetry with the messages path and to keep route shape in config.
    ORBITAL_REPORT_PATH_TEMPLATE: str = "/reports/{report_id}"

    # Per-request HTTP timeout in seconds. Exposed as a setting so ops can tune
    # it without a redeploy if the upstream gets slow.
    ORBITAL_HTTP_TIMEOUT_SECONDS: float = 10.0

    # Normalise path settings so a missing leading slash doesn't silently
    # break URL joining against the base URL. This is much friendlier than
    # having ops debug a 404 caused by `messages/current-period` being
    # treated as relative by httpx.
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
    """Return a process-wide cached Settings instance.

    `lru_cache` avoids re-parsing the .env file on every call and gives us a
    single object to monkeypatch in tests via `get_settings.cache_clear()`.
    """
    return Settings()


settings = get_settings()
