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
    # Key for the encrypted copy of staff passwords the developer can read. Empty = derived from JWT_SECRET_KEY.
    PASSWORD_VAULT_KEY: str = Field(default="")
    # Activity-log rows older than this many days are deleted every night (0 = keep everything). Keeps the table small and fast.
    AUDIT_KEEP_DAYS: int = Field(default=60, ge=0)
    # The time zone the audit screens and date/time filters use (stored times are always UTC).
    DISPLAY_TIMEZONE: str = Field(default="Asia/Kolkata")
    # Entry Contributors may NOT edit or delete a submitted entry (corrections go to a Team Lead / administrator). Set true only to bring back the old
    # "employee corrects their own entry" behaviour; every such change is still written to the entry history.
    EMPLOYEE_CAN_CORRECT_OWN: bool = Field(default=False)

    # "Forgot password" by emailed one-time code. Free with a Gmail account + App Password (smtp.gmail.com:587). Empty SMTP_HOST = feature off.
    SMTP_HOST: str = Field(default="")
    SMTP_PORT: int = Field(default=587)
    SMTP_USER: str = Field(default="")
    SMTP_PASSWORD: str = Field(default="")
    SMTP_FROM: str = Field(default="")             # defaults to SMTP_USER
    RESET_CODE_MINUTES: int = Field(default=10, ge=1, le=60)
    RESET_CODE_MAX_ATTEMPTS: int = Field(default=5, ge=1, le=10)
    RESET_CODE_MAX_PER_HOUR: int = Field(default=3, ge=1, le=20)
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
    # --- Upload policy (all enforced by the server; the web app reads them from GET /uploads/policy) ---
    # What the server will ACCEPT from a client. A raw phone photo is 2-8 MB and the installed Android app does not shrink
    # photos before sending, so this stays generous; the real limit is what gets STORED (below).
    COMPLIANCE_MAX_FILE_MB: int = Field(default=12, ge=1, le=100)
    PHOTO_MAX_STORED_KB: int = Field(default=1024, ge=100, le=10_240)   # a stored photo is never larger than this (it is re-encoded to fit)
    PDF_MAX_FILE_MB: int = Field(default=2, ge=1, le=100)               # a PDF is stored exactly as uploaded, so this is a hard limit
    # Photos are resized and re-encoded before they are stored (~300 KB typical).
    IMAGE_OPTIMIZE: bool = Field(default=True)
    IMAGE_MAX_DIMENSION: int = Field(default=1600, ge=600, le=4000)     # longest side, pixels
    IMAGE_JPEG_QUALITY: int = Field(default=80, ge=50, le=95)
    IMAGE_KEEP_BELOW_KB: int = Field(default=350, ge=0)                 # an image this small, upright and without GPS is not recompressed
    # Only used to WARN in the logs and the audit report. It is not enforced and not the price list.
    STORAGE_QUOTA_GB: float = Field(default=5.0, gt=0)
    STORAGE_WARN_PERCENT: int = Field(default=80, ge=1, le=100)
    FIREBASE_CREDENTIALS_FILE: str = Field(default="")
    FIREBASE_CREDENTIALS_JSON: str = Field(default="")                  # the same service-account key as the file, as one JSON string (a Fly secret)
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
    # Work starts at 10:00 and nobody is marked late until after 10:30 (10:00 + 30 minutes). Checking in at or before 10:30 marks nothing.
    ATTENDANCE_GRACE_MINUTES: int = Field(default=30)

    # Vendor cards
    COMPANY_NAME: str = Field(default="VEE KAY AQUATECH PVT. LTD.")
    COMPANY_TAGLINE: str = Field(default="Packaged Drinking Water")
    COMPANY_EMAIL: str = Field(default="info1.veekayaquatech@gmail.com")
    CARDS_FIRST_MONTH: str = Field(default="2026-09")
    CARD_LOGO_PATH: str = Field(default="")
    PUBLIC_APP_URL: str = Field(default="http://localhost:5173")
    QR_SIGNING_SECRET: str = Field(default="")

    # Order marking
    # Last month's data often takes a few days to finish. For this many days at the start of a month employees may still mark
    # LAST month's dates (the 1st to the Nth). 0 switches it off. Admins can always mark any past date.
    BACKMONTH_GRACE_DAYS: int = Field(default=7, ge=0, le=28)
    MIN_BOTTLE_COUNT: int = 0
    MAX_BOTTLE_COUNT: int = 300

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