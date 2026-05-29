"""
ManatAds – Live DB Migration: add new tables safely
=============================================================
Run ONCE inside the production container to append new tables.

Safe by design:
  • Uses SQLAlchemy's Base.metadata.create_all().
  • Automatically skips existing tables, preserving all user data.
  • Zero downtime – can be executed while the bot is running.

Usage:
    python migrate_db.py
"""

from __future__ import annotations

import asyncio
import logging
import sys

from dotenv import load_dotenv

# ── Bootstrap ──────────────────────────────────────────────────────────
load_dotenv()

# Import after load_dotenv so DATABASE_URL is resolved from .env
from database import engine  # noqa: E402
from models import Base  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
)
logger = logging.getLogger("migrate_db")


async def run_migration() -> None:
    logger.info("Starting migration: synchronizing database schema...")

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
        logger.info("Migration complete. All new tables created safely. Existing data retains intact.")
    except Exception as e:
        logger.error("Migration failed: %s", e)
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_migration())
