from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Централизованное хранилище настроек приложения.
    Валидирует переменные окружения при старте (Fail-Fast).
    """
    model_config = SettingsConfigDict(
        env_file=".env", 
        extra="ignore"
    )

    # --- Database Settings ---
    db_host: str = "localhost"
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_name: str
    db_user: str
    db_password: SecretStr

    # --- Profiler Settings ---
    profiler_threshold: int = Field(default=100_000, ge=0)

# Создаётся один раз при первом импорте app.config
settings = Settings()