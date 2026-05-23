"""
ManatAds – Async Database Engine & Session Factory
===================================================
Reads DATABASE_URL from the environment.
  • If set → connects to PostgreSQL via asyncpg.
  • If empty / missing → falls back to a local SQLite file (dev mode).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

load_dotenv()

# ── Resolve database URL ────────────────────────────────────────────────
_raw_url = os.getenv("DATABASE_URL", "").strip()

if _raw_url:
    # Production: PostgreSQL via asyncpg
    DATABASE_URL: str = _raw_url
    _connect_args: dict = {}
else:
    # Development: local SQLite file
    _db_path = Path(__file__).resolve().parent / "manat_ads.db"
    DATABASE_URL = f"sqlite+aiosqlite:///{_db_path}"
    _connect_args = {"check_same_thread": False}

# ── Dialect flag (used by other modules for UPSERT branching) ───────
DB_IS_POSTGRES: bool = "postgresql" in DATABASE_URL

# ── Engine & session factory ────────────────────────────────────────────
engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("ENVIRONMENT", "development") == "development",
    connect_args=_connect_args,
    pool_pre_ping=True,
)

async_session = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Declarative base ───────────────────────────────────────────────────
class Base(AsyncAttrs, DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


# ── Lifecycle helpers ──────────────────────────────────────────────────
async def init_db() -> None:
    """Create all tables that don't yet exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose of the connection pool gracefully."""
    await engine.dispose()
