"""
Central application settings.

All configuration is read from environment variables (via .env in dev).
Nothing here is hard-coded per the "no hard-coded secrets/URLs" rule.
"""
from functools import lru_cache
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Refresh-token cookie (HttpOnly; used by the web app, which sends `X-Auth-Mode: cookie`)
    REFRESH_COOKIE_NAME: str = "vk_refresh"
    REFRESH_COOKIE_SAMESITE: str = "lax"     # lax | strict | none ("none" only if the API and web app are on different sites)
    REFRESH_COOKIE_SECURE: bool | None = Field(default=None)   # None = secure in production, off for local http

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
    # Files are handed to the browser as short-lived signed links straight from the bucket, so the API never streams them.
    S3_URL_EXPIRE_SECONDS: int = Field(default=300, ge=30, le=3600)

    # ---- Database connection pool (per worker process) ----
    DB_POOL_SIZE: int = Field(default=10, ge=1, le=50)
    DB_MAX_OVERFLOW: int = Field(default=20, ge=0, le=100)
    DB_POOL_RECYCLE_SECONDS: int = Field(default=1800, ge=30)

    # ---- Read cache for the dashboard roll-ups (seconds; 0 turns it off) ----
    DASHBOARD_CACHE_SECONDS: int = Field(default=30, ge=0, le=600)

    # ---- Test reports (water tests, valid for six months) ----
    # Platforms that accept test reports. Blinkit is off for now: add "blinkit" here to switch it on.
    TEST_REPORT_PLATFORMS: list[str] = Field(default_factory=lambda: ["zepto"])
    TEST_REPORT_ALERT_DAYS: int = Field(default=30, ge=1, le=120)   # warn this many days before a report expires

    # ---- Attendance ----
    ATTENDANCE_TIMEZONE: str = Field(default="Asia/Kolkata")   # which local day a sign-in belongs to
    ATTENDANCE_ACTIVE_WINDOW_MINUTES: int = Field(default=30)  # still 'active' if seen this recently
    OFFICE_DEFAULT_RADIUS_M: int = Field(default=100)
    # Shared secret for tickets pushed in from outside (e.g. a Google Apps Script). Empty = that endpoint is switched off.
    TICKET_WEBHOOK_KEY: str = Field(default="")
    # Bottle QR tracking. BOTTLE_API_KEY lets a partner's / third-party scanner system push scans and read bottle data
    # (header X-Integration-Key); empty = that API is switched off. A bottle scanned IN to a store and not scanned OUT
    # within BOTTLE_LOST_AFTER_DAYS is reported as overdue (possibly lost).
    # Access code for the developer-only "Cards from sheet" tool (checked on the server, rate-limited). Change it in production.
    CARD_SHEET_CODE: str = Field(default="2580")
    BOTTLE_API_KEY: str = Field(default="")
    BOTTLE_LOST_AFTER_DAYS: int = Field(default=30)
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

    # ---- Order sync from Google Sheets ----
    # Same "<partner_slug>=<spreadsheet_id>[:<gid>]" format, but a platform may appear more than once
    # (one entry per month tab). Each sheet is "one row per store, one column per date".
    #   ORDER_SYNC_SHEETS='["blinkit=1AbC...:0","blinkit=1AbC...:123456","zepto=1XyZ...:0"]'
    ORDER_SYNC_SHEETS: list[str] = Field(default_factory=list)
    ORDER_SYNC_ENABLED: bool = Field(default=True)      # run it right after the daily store sync
    # Off (default): a day that already has a different count is kept. On: the sheet replaces it.
    ORDER_SYNC_OVERWRITE: bool = Field(default=False)

    @model_validator(mode="after")
    def _refuse_unsafe_production(self) -> "Settings":
        """Fail fast at boot rather than run a production server with dev-grade settings."""
        if self.ENVIRONMENT.strip().lower() != "production":
            return self
        problems: list[str] = []
        if len(self.JWT_SECRET_KEY) < 32 or "change-me" in self.JWT_SECRET_KEY.lower():
            problems.append("JWT_SECRET_KEY must be a random value of at least 32 characters")
        if any("localhost" in o or "127.0.0.1" in o for o in self.CORS_ORIGINS) or "*" in self.CORS_ORIGINS:
            problems.append("CORS_ORIGINS must list only your real https frontend origin(s)")
        if any(o.startswith("http://") for o in self.CORS_ORIGINS):
            problems.append("CORS_ORIGINS must use https://")
        if "localhost" in self.PUBLIC_APP_URL or "127.0.0.1" in self.PUBLIC_APP_URL:
            problems.append("PUBLIC_APP_URL must be the public frontend URL (it is printed in every card QR code)")
        if self.DEBUG:
            problems.append("DEBUG must be false")
        if self.BCRYPT_ROUNDS < 12:
            problems.append("BCRYPT_ROUNDS must be at least 12")
        if self.STORAGE_BACKEND == "s3" and not (self.S3_BUCKET and self.S3_ACCESS_KEY_ID and self.S3_SECRET_ACCESS_KEY):
            problems.append("STORAGE_BACKEND=s3 needs S3_BUCKET, S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY")
        if problems:
            raise ValueError("Unsafe production configuration: " + "; ".join(problems))
        return self

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

    def order_sheet_sources(self) -> dict[str, list[tuple[str, str]]]:
        """{partner_slug: [(spreadsheet_id, gid), ...]} parsed from ORDER_SYNC_SHEETS."""
        out: dict[str, list[tuple[str, str]]] = {}
        for raw in self.ORDER_SYNC_SHEETS:
            if "=" not in raw:
                continue
            slug, ref = raw.split("=", 1)
            sheet_id, _, gid = ref.strip().partition(":")
            if sheet_id.strip():
                out.setdefault(slug.strip().lower(), []).append((sheet_id.strip(), gid.strip() or "0"))
        return out


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
