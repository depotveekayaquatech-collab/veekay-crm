"""
Database engine + session factory. Never instantiate Session directly
elsewhere — always go through get_db (FastAPI dependency) so sessions
are properly closed and requests are isolated from each other.
"""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_recycle=settings.DB_POOL_RECYCLE_SECONDS,   # never reuse a connection the server may have dropped
    pool_timeout=settings.DB_POOL_TIMEOUT_SECONDS,
    connect_args={
        "connect_timeout": settings.DB_CONNECT_TIMEOUT_SECONDS,
        "keepalives": 1,
        "keepalives_idle": settings.DB_KEEPALIVE_IDLE_SECONDS,
        "keepalives_interval": 10,
        "keepalives_count": 3,
        "tcp_user_timeout": 20_000,     # ms: unacknowledged data older than this closes the socket (libpq 12+)
    },
    future=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
