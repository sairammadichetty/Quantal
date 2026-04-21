from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    # App Settings
    APP_NAME: str = "Orbital Copilot Usage API"
    DEBUG: bool = False
    
    # External API Base URLs
    # Using the URLs from your technical task as defaults
    ORBITAL_BASE_URL: str = "https://windows.net"
    
    # Pydantic Settings Config
    model_config = SettingsConfigDict(
        # Looks for a .env file in the project root
        env_file=".env", 
        # Optional: ignores extra environment variables not defined here
        extra="ignore",
        # Case-sensitive matching for env vars
        case_sensitive=True
    )

@lru_cache()
def get_settings():
    """
    Creates a cached instance of settings.
    Using lru_cache ensures we don't re-read the .env file on every call.
    """
    return Settings()

# Global settings instance for easy importing
settings = get_settings()
