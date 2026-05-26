"""
ManatAds – Migration: Add `language` column to `users` table
==============================================================
Standalone migration script.  Works with both SQLite and PostgreSQL.

Usage:
    python migrate_add_language.py
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from database import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migrate_add_language")

SQL = "ALTER TABLE users ADD COLUMN language VARCHAR(5) DEFAULT 'az'"


async def migrate() -> None:
    """Add the `language` column if it does not already exist."""
    async with engine.begin() as conn:
        try:
            await conn.execute(text(SQL))
            logger.info("Column 'language' added to 'users' table successfully.")
        except Exception as exc:
            # Column already exists – safe to ignore
            msg = str(exc).lower()
            if "duplicate column" in msg or "already exists" in msg:
                logger.info("Column 'language' already exists – skipping.")
            else:
                logger.error("Migration failed: %s", exc)
                raise


if __name__ == "__main__":
    asyncio.run(migrate())
