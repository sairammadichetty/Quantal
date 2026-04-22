from functools import lru_cache

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

    # Per-request HTTP timeout in seconds. Exposed as a setting so ops can tune
    # it without a redeploy if the upstream gets slow.
    ORBITAL_HTTP_TIMEOUT_SECONDS: float = 10.0

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=True,
    )


@lru_cache()
def get_settings() -> Settings:
    """Return a process-wide cached Settings instance.

    `lru_cache` avoids re-parsing the .env file on every call and gives us a
    single object to monkeypatch in tests via `get_settings.cache_clear()`.
    """
    return Settings()


settings = get_settings()
