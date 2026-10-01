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
    PASSWORD_MIN_LENGTH: int = 10
    REFRESH_REUSE_GRACE_SECONDS: int = 15   # tolerate two tabs refreshing with the same token at once
    LOGIN_IP_MAX_FAILURES: int = 20         # failed logins per IP per window before it is blocked
    LOGIN_IP_WINDOW_MINUTES: int = 10
    TRUST_PROXY_HEADERS: bool = False       # set true behind a reverse proxy (Render) so the real client IP is used
    BOOTSTRAP_ADMIN_PASSWORD: str = Field(default="")  # production seed: creates ADMIN001 with this password (forced change)
    MAX_FAILED_LOGIN_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15

    # CORS
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # File uploads (tickets / damaged bottle photos)
    MAX_UPLOAD_SIZE_MB: int = 8
    ALLOWED_UPLOAD_CONTENT_TYPES: list[str] = Field(
        default_factory=lambda: ["image/jpeg", "image/png", "image/webp"]
    )

    # ---- Compliance / bill file storage ----
    # Local folder for uploaded cards & bills (relative paths resolve from the
    # backend working dir). On hosts with an ephemeral disk, point this at a
    # persistent volume — or swap app/core/storage.py for object storage.
    UPLOAD_DIR: str = Field(default="storage")
    COMPLIANCE_MAX_FILE_MB: int = Field(default=12)
    BILL_DUE_DAYS_AFTER_MONTH_END: int = Field(default=45)
    COMPLIANCE_EARLIEST_MONTH: str = Field(default="2026-06")  # cards/bills start here
    COMPLIANCE_MAX_MONTHS_BACK: int = Field(default=12)

    # ---- Security / operations ----
    BCRYPT_ROUNDS: int = Field(default=12)              # tests lower this; production keeps 12
    SECURITY_HEADERS_ENABLED: bool = Field(default=True)
    DOCS_ENABLED: bool | None = Field(default=None)     # None = on in development, off in production
    MAX_REQUEST_BYTES: int = Field(default=150 * 1024 * 1024)   # largest accepted request body (bulk uploads)
    RATE_LIMIT_ENABLED: bool = Field(default=True)
    RATE_LIMIT_DEFAULT_PER_MIN: int = Field(default=600)    # any API call, per client IP
    RATE_LIMIT_HEAVY_PER_MIN: int = Field(default=30)       # uploads, imports, PDF / Excel generation, per client IP
    RATE_LIMIT_PUBLIC_PER_MIN: int = Field(default=60)      # unauthenticated endpoints (QR page)
    LOG_LEVEL: str = Field(default="INFO")
    LOG_JSON: bool | None = Field(default=None)         # None = JSON lines in production, readable text otherwise
    SENTRY_DSN: str = Field(default="")                 # set to forward unhandled errors to Sentry
    RELEASE: str = Field(default="")                    # e.g. the git commit; tags logs / Sentry events

    # ---- File storage ----
    STORAGE_BACKEND: str = Field(default="local")       # local | s3 (any S3-compatible service: AWS, Cloudflare R2, Backblaze, MinIO)
    S3_BUCKET: str = Field(default="")
    S3_ENDPOINT_URL: str = Field(default="")            # blank for AWS; set for R2 / Backblaze / MinIO
    S3_REGION: str = Field(default="auto")
    S3_ACCESS_KEY_ID: str = Field(default="")
    S3_SECRET_ACCESS_KEY: str = Field(default="")
    S3_PREFIX: str = Field(default="veekay/")

    # ---- Attendance ----
    ATTENDANCE_TIMEZONE: str = Field(default="Asia/Kolkata")   # which local day a sign-in belongs to
    ATTENDANCE_ACTIVE_WINDOW_MINUTES: int = Field(default=30)  # still 'active' if seen this recently
    OFFICE_DEFAULT_RADIUS_M: int = Field(default=100)
    ATTENDANCE_WORK_START: str = Field(default="10:00")        # HH:MM local time; checking in later than start + grace is "late"
    ATTENDANCE_GRACE_MINUTES: int = Field(default=15)

    # ---- Vendor cards ----
    COMPANY_NAME: str = Field(default="VEE KAY AQUATECH PVT. LTD.")
    COMPANY_TAGLINE: str = Field(default="Packaged Drinking Water")
    COMPANY_EMAIL: str = Field(default="info1.veekayaquatech@gmail.com")   # printed on every card
    CARDS_FIRST_MONTH: str = Field(default="2026-09")   # earliest month a card can be filled for / shown as "last month"
    CARD_LOGO_PATH: str = Field(default="")             # override the logo printed on cards / PDFs (default: app/assets/watr-logo.png)
    # Base URL of the web app. The QR code on each card opens <PUBLIC_APP_URL>/count?...
    PUBLIC_APP_URL: str = Field(default="http://localhost:5173")
    QR_SIGNING_SECRET: str = Field(default="")          # falls back to JWT_SECRET_KEY

    # ---- Order marking ----
    MIN_BOTTLE_COUNT: int = 0
    MAX_BOTTLE_COUNT: int = 200

    # Partner platforms (by slug) that use the employee-model: no region
    # concept, stores routed purely by state -> employee assignment.
    EMPLOYEE_MODEL_PLATFORM_SLUGS: list[str] = Field(default_factory=lambda: ["zepto"])
    # Platforms where a state may be assigned to any employee regardless of
    # the employee's home region (the region label is informational only).
    REGION_INDEPENDENT_PLATFORM_SLUGS: list[str] = Field(default_factory=lambda: ["zepto"])

    # ---- Store sync from Google Sheets ----
    # Each entry: "<partner_slug>=<spreadsheet_id>[:<gid>]". The sheet must be
    # shared as "Anyone with the link - Viewer" (or Published to web); the
    # backend reads it via the public CSV export endpoint. Example:
    #   STORE_SYNC_SHEETS='["blinkit=12fo5ar...:0","zepto=1xlxl4...:0"]'
    STORE_SYNC_SHEETS: list[str] = Field(default_factory=list)
    STORE_SYNC_ENABLED: bool = Field(default=True)      # run the daily job
    STORE_SYNC_HOUR: int = Field(default=10)            # local hour, 24h
    STORE_SYNC_MINUTE: int = Field(default=0)
    STORE_SYNC_TIMEZONE: str = Field(default="Asia/Kolkata")

    def sheet_sources(self) -> dict[str, tuple[str, str]]:
        """{partner_slug: (spreadsheet_id, gid)} parsed from STORE_SYNC_SHEETS."""
        out: dict[str, tuple[str, str]] = {}
        for raw in self.STORE_SYNC_SHEETS:
            if "=" not in raw:
                continue
            slug, ref = raw.split("=", 1)
            sheet_id, _, gid = ref.strip().partition(":")
            out[slug.strip().lower()] = (sheet_id.strip(), gid.strip() or "0")
        return out


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
