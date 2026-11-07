from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Cada Hora Cuenta API"
    app_env: str = "development"
    database_url: str = "sqlite:///./backend-local.db"
    rpa_api_key: str = Field(default="dev-rpa-key-change-this-0001", min_length=24)
    user_api_key: str = Field(default="dev-user-key-change-this-001", min_length=24)
    supabase_jwt_secret: str | None = None
    allowed_origins: str = "http://localhost:5173"

    @property
    def origins(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @model_validator(mode="after")
    def secure_production(self) -> "Settings":
        if self.is_production:
            if self.is_sqlite:
                raise ValueError("Producción requiere PostgreSQL/Supabase, no SQLite")
            if self.rpa_api_key.startswith("dev-") or self.user_api_key.startswith("dev-"):
                raise ValueError("Producción requiere credenciales propias")
            if not self.supabase_jwt_secret:
                raise ValueError("Producción requiere SUPABASE_JWT_SECRET")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
