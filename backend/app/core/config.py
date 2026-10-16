"""
Central application settings.

All configuration is read from environment variables (via .env in dev).
Nothing here is hard-coded per the "no hard-coded secrets/URLs" rule.
"""

import json
from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Environment
    ENVIRONMENT: str = Field(default="development")  # development | staging | production
    DEBUG: bool = Field(default=False)

    # App
    PROJECT_NAME: str = "Aquatrack"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+psycopg://veekay:veekay@localhost:5432/veekay_crm"
    )

    @field_validator("DATABASE_URL")
    @classmethod
    def _use_psycopg3_driver(cls, value: str) -> str:
        # Normalize managed PostgreSQL URLs for psycopg v3.
        if value.startswith("postgres://"):
            value = "postgresql://" + value[len("postgres://") :]
        if value.startswith("postgresql://"):
            value = "postgresql+psycopg://" + value[len("postgresql://") :]
        return value

    # Auth / JWT
    JWT_SECRET_KEY: str = Field(...)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14

    # Refresh-token cookie
    REFRESH_COOKIE_NAME: str = "vk_refresh"
    REFRESH_COOKIE_SAMESITE: str = "lax"
    REFRESH_COOKIE_SECURE: bool | None = Field(default=None)

    # Login protection
    PASSWORD_MIN_LENGTH: int = 10
    REFRESH_REUSE_GRACE_SECONDS: int = 15
    LOGIN_IP_MAX_FAILURES: int = 20
    LOGIN_IP_WINDOW_MINUTES: int = 10
    TRUST_PROXY_HEADERS: bool = False
    BOOTSTRAP_ADMIN_PASSWORD: str = Field(default="")
    MAX_FAILED_LOGIN_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15

    # CORS
    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value):
        """Accept JSON arrays or comma-separated CORS origins."""
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass

            return [
                origin.strip()
                for origin in value.split(",")
                if origin.strip()
            ]

        return value

    # File uploads (tickets / damaged bottle photos)
    MAX_UPLOAD_SIZE_MB: int = 8
    ALLOWED_UPLOAD_CONTENT_TYPES: list[str] = Field(
        default_factory=lambda: ["image/jpeg", "image/png", "image/webp"]
    )

    # Compliance / bill file storage
    UPLOAD_DIR: str = Field(default="storage")
    COMPLIANCE_MAX_FILE_MB: int = Field(default=12)
    FIREBASE_CREDENTIALS_FILE: str = Field(default="")
    BILL_DUE_DAYS_AFTER_MONTH_END: int = Field(default=45)
    COMPLIANCE_EARLIEST_MONTH: str = Field(default="2026-06")
    COMPLIANCE_MAX_MONTHS_BACK: int = Field(default=12)

    # Security / operations
    BCRYPT_ROUNDS: int = Field(default=12)
    SECURITY_HEADERS_ENABLED: bool = Field(default=True)
    DOCS_ENABLED: bool | None = Field(default=None)
    MAX_REQUEST_BYTES: int = Field(default=150 * 1024 * 1024)
    RATE_LIMIT_ENABLED: bool = Field(default=True)
    RATE_LIMIT_DEFAULT_PER_MIN: int = Field(default=600)
    RATE_LIMIT_HEAVY_PER_MIN: int = Field(default=30)
    RATE_LIMIT_PUBLIC_PER_MIN: int = Field(default=60)
    LOG_LEVEL: str = Field(default="INFO")
    LOG_JSON: bool | None = Field(default=None)
    SENTRY_DSN: str = Field(default="")
    RELEASE: str = Field(default="")

    # File storage
    STORAGE_BACKEND: str = Field(default="local")
    S3_BUCKET: str = Field(default="")
    S3_ENDPOINT_URL: str = Field(default="")
    S3_REGION: str = Field(default="auto")
    S3_ACCESS_KEY_ID: str = Field(default="")
    S3_SECRET_ACCESS_KEY: str = Field(default="")
    S3_PREFIX: str = Field(default="veekay/")
    S3_URL_EXPIRE_SECONDS: int = Field(default=300, ge=30, le=3600)

    # Database connection pool
    DB_POOL_SIZE: int = Field(default=10, ge=1, le=50)
    DB_MAX_OVERFLOW: int = Field(default=20, ge=0, le=100)
    DB_POOL_RECYCLE_SECONDS: int = Field(default=1800, ge=30)
    # How long a request waits for a free pooled connection / a new connection to the database before giving up.
    # Without a bound an overloaded pool makes every request hang for a minute or more instead of failing fast.
    DB_POOL_TIMEOUT_SECONDS: int = Field(default=15, ge=1, le=120)
    DB_CONNECT_TIMEOUT_SECONDS: int = Field(default=10, ge=1, le=60)
    # TCP keepalives on database connections: an idle pooled connection that a NAT / proxy silently dropped is noticed
    # after about idle + interval*count seconds, instead of the first query after the pause hanging on a dead socket.
    DB_KEEPALIVE_IDLE_SECONDS: int = Field(default=30, ge=5, le=600)

    # Dashboard cache
    DASHBOARD_CACHE_SECONDS: int = Field(default=30, ge=0, le=600)

    # Test reports
    TEST_REPORT_PLATFORMS: list[str] = Field(
        default_factory=lambda: ["zepto"]
    )
    TEST_REPORT_ALERT_DAYS: int = Field(default=30, ge=1, le=120)

    # Attendance
    ATTENDANCE_TIMEZONE: str = Field(default="Asia/Kolkata")
    ATTENDANCE_ACTIVE_WINDOW_MINUTES: int = Field(default=30)
    OFFICE_DEFAULT_RADIUS_M: int = Field(default=100)

    # Ticket integration
    TICKET_WEBHOOK_KEY: str = Field(default="")

    # Bottle QR tracking
    CARD_SHEET_CODE: str = Field(default="2580")
    BOTTLE_API_KEY: str = Field(default="")
    BOTTLE_LOST_AFTER_DAYS: int = Field(default=30)

    ATTENDANCE_WORK_START: str = Field(default="10:00")
    ATTENDANCE_GRACE_MINUTES: int = Field(default=15)

    # Vendor cards
    COMPANY_NAME: str = Field(default="VEE KAY AQUATECH PVT. LTD.")
    COMPANY_TAGLINE: str = Field(default="Packaged Drinking Water")
    COMPANY_EMAIL: str = Field(default="info1.veekayaquatech@gmail.com")
    CARDS_FIRST_MONTH: str = Field(default="2026-09")
    CARD_LOGO_PATH: str = Field(default="")
    PUBLIC_APP_URL: str = Field(default="http://localhost:5173")
    QR_SIGNING_SECRET: str = Field(default="")

    # Order marking
    MIN_BOTTLE_COUNT: int = 0
    MAX_BOTTLE_COUNT: int = 200

    # Partner platform configuration
    EMPLOYEE_MODEL_PLATFORM_SLUGS: list[str] = Field(
        default_factory=lambda: ["zepto"]
    )
    REGION_INDEPENDENT_PLATFORM_SLUGS: list[str] = Field(
        default_factory=lambda: ["zepto"]
    )

    # Store sync from Google Sheets
    STORE_SYNC_SHEETS: list[str] = Field(default_factory=list)
    STORE_SYNC_ENABLED: bool = Field(default=True)
    # False = the daily job does NOT pull the sheets (a developer's "Sync now" still does). Bill reminders keep running.
    SHEET_AUTO_SYNC: bool = Field(default=True)
    # Service-account key (JSON text) for PRIVATE sheets. Secret: set it with `fly secrets set`, never in a file.
    GOOGLE_SERVICE_ACCOUNT_JSON: str = Field(default="", repr=False)
    SYNC_TRIGGER_KEY: str = Field(default="")
    STORE_SYNC_HOUR: int = Field(default=10)
    STORE_SYNC_MINUTE: int = Field(default=0)
    STORE_SYNC_TIMEZONE: str = Field(default="Asia/Kolkata")

    # Order sync from Google Sheets
    ORDER_SYNC_SHEETS: list[str] = Field(default_factory=list)
    ORDER_SYNC_ENABLED: bool = Field(default=True)
    ORDER_SYNC_OVERWRITE: bool = Field(default=False)

    @model_validator(mode="after")
    def _refuse_unsafe_production(self) -> "Settings":
        """Reject unsafe configuration before running in production."""

        # Normalize CORS origins and whitelist the public application URL.
        normalized_cors: list[str] = []

        for origin in self.CORS_ORIGINS:
            cleaned = origin.strip().rstrip("/")
            if cleaned and cleaned not in normalized_cors:
                normalized_cors.append(cleaned)

        public_origin = self.PUBLIC_APP_URL.strip().rstrip("/")
        if public_origin and public_origin not in normalized_cors:
            normalized_cors.append(public_origin)

        self.CORS_ORIGINS = normalized_cors

        if self.ENVIRONMENT.strip().lower() != "production":
            return self

        problems: list[str] = []

        if (
            len(self.JWT_SECRET_KEY) < 32
            or "change-me" in self.JWT_SECRET_KEY.lower()
        ):
            problems.append(
                "JWT_SECRET_KEY must be a random value of at least 32 characters"
            )

        if (
            any(
                "localhost" in origin or "127.0.0.1" in origin
                for origin in self.CORS_ORIGINS
            )
            or "*" in self.CORS_ORIGINS
        ):
            problems.append(
                "CORS_ORIGINS must list only your real https frontend origin(s)"
            )

        if any(origin.startswith("http://") for origin in self.CORS_ORIGINS):
            problems.append("CORS_ORIGINS must use https://")

        if (
            "localhost" in self.PUBLIC_APP_URL
            or "127.0.0.1" in self.PUBLIC_APP_URL
        ):
            problems.append(
                "PUBLIC_APP_URL must be the public frontend URL "
                "(it is printed in every card QR code)"
            )

        if not self.PUBLIC_APP_URL.startswith("https://"):
            problems.append(
                "PUBLIC_APP_URL must start with https:// in production "
                "(printed in every card QR code)"
            )

        if self.DEBUG:
            problems.append("DEBUG must be false")

        if self.BCRYPT_ROUNDS < 12:
            problems.append("BCRYPT_ROUNDS must be at least 12")

        if self.STORAGE_BACKEND == "s3" and not (
            self.S3_BUCKET
            and self.S3_ACCESS_KEY_ID
            and self.S3_SECRET_ACCESS_KEY
        ):
            problems.append(
                "STORAGE_BACKEND=s3 needs S3_BUCKET, "
                "S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY"
            )

        if problems:
            raise ValueError(
                "Unsafe production configuration: " + "; ".join(problems)
            )

        return self

    def sheet_sources(self) -> dict[str, tuple[str, str]]:
        """Return {partner_slug: (spreadsheet_id, gid)}."""
        out: dict[str, tuple[str, str]] = {}

        for raw in self.STORE_SYNC_SHEETS:
            if "=" not in raw:
                continue

            slug, ref = raw.split("=", 1)
            sheet_id, _, gid = ref.strip().partition(":")
            out[slug.strip().lower()] = (
                sheet_id.strip(),
                gid.strip() or "0",
            )

        return out

    def order_sheet_sources(self) -> dict[str, list[tuple[str, str]]]:
        """Return {partner_slug: [(spreadsheet_id, gid), ...]}."""
        out: dict[str, list[tuple[str, str]]] = {}

        for raw in self.ORDER_SYNC_SHEETS:
            if "=" not in raw:
                continue

            slug, ref = raw.split("=", 1)
            sheet_id, _, gid = ref.strip().partition(":")

            if sheet_id.strip():
                out.setdefault(slug.strip().lower(), []).append(
                    (sheet_id.strip(), gid.strip() or "0")
                )

        return out


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()