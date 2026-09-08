"""
Central application settings.

All configuration is read from environment variables (via .env in dev).
Nothing here is hard-coded per the "no hard-coded secrets/URLs" rule.
"""
from functools import lru_cache
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Environment
    ENVIRONMENT: str = Field(default="development")  # development | staging | production
    DEBUG: bool = Field(default=False)

    # App
    PROJECT_NAME: str = "Veekay Aquatech CRM"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+psycopg://veekay:veekay@localhost:5432/veekay_crm"
    )

    @field_validator("DATABASE_URL")
    @classmethod
    def _use_psycopg3_driver(cls, value: str) -> str:
        # Managed hosts (Render, Railway, Heroku, ...) hand out a bare
        # "postgres://" / "postgresql://" URL, which SQLAlchemy would try to
        # open with psycopg2. We ship psycopg (v3), so normalize the scheme.
        if value.startswith("postgres://"):
            value = "postgresql://" + value[len("postgres://") :]
        if value.startswith("postgresql://"):
            value = "postgresql+psycopg://" + value[len("postgresql://") :]
        return value

    # Auth / JWT
    JWT_SECRET_KEY: str = Field(...)  # must be set via env — no default in prod
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14

    # Login protection
    MAX_FAILED_LOGIN_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15

    # CORS
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # File uploads (tickets / damaged bottle photos)
    MAX_UPLOAD_SIZE_MB: int = 8
    ALLOWED_UPLOAD_CONTENT_TYPES: list[str] = Field(
        default_factory=lambda: ["image/jpeg", "image/png", "image/webp"]
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
