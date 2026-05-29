"""
ManatAds – Live DB Migration: add `cooldown_notified` column
=============================================================
Run ONCE inside the production container to append the new column
introduced in the 3-hour Professional Cooldown upgrade.

Safe by design:
  • Uses ALTER TABLE … ADD COLUMN IF NOT EXISTS (PostgreSQL ≥ 9.6).
  • For SQLite, checks via PRAGMA before issuing ALTER TABLE (SQLite
    does not support IF NOT EXISTS on ALTER TABLE).
  • Existing rows are automatically backfilled to DEFAULT TRUE,
    meaning "already notified" – no spurious push notifications fire.
  • Zero downtime – can be executed while the bot is running.

Usage (inside the VPS container):
    python migrate_db.py
"""

from __future__ import annotations

import asyncio
import logging
import sys

from dotenv import load_dotenv
from sqlalchemy import text

# ── Bootstrap ──────────────────────────────────────────────────────────
load_dotenv()

# Import after load_dotenv so DATABASE_URL is resolved from .env
from database import DB_IS_POSTGRES, engine  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
)
logger = logging.getLogger("migrate_db")

# ── Target table & column (must match models.py) ───────────────────────
TABLE_NAME  = "users"           # User.__tablename__
COLUMN_NAME = "cooldown_notified"


async def run_migration() -> None:
    logger.info("Starting migration: add '%s' to table '%s'.", COLUMN_NAME, TABLE_NAME)
    logger.info("Database dialect: %s", "PostgreSQL" if DB_IS_POSTGRES else "SQLite")

    async with engine.begin() as conn:

        if DB_IS_POSTGRES:
            # ── PostgreSQL: single idempotent statement ────────────────
            sql = text(
                f"ALTER TABLE {TABLE_NAME} "
                f"ADD COLUMN IF NOT EXISTS {COLUMN_NAME} BOOLEAN DEFAULT TRUE;"
            )
            await conn.execute(sql)
            logger.info(
                "PostgreSQL: ALTER TABLE executed. "
                "Column '%s' added (or already existed) with DEFAULT TRUE.",
                COLUMN_NAME,
            )

        else:
            # ── SQLite: check PRAGMA first (no IF NOT EXISTS support) ──
            pragma_result = await conn.execute(text(f"PRAGMA table_info({TABLE_NAME});"))
            columns = [row[1] for row in pragma_result.fetchall()]  # row[1] = column name

            if COLUMN_NAME in columns:
                logger.info(
                    "SQLite: Column '%s' already exists in '%s'. Nothing to do.",
                    COLUMN_NAME, TABLE_NAME,
                )
            else:
                sql = text(
                    f"ALTER TABLE {TABLE_NAME} "
                    f"ADD COLUMN {COLUMN_NAME} BOOLEAN DEFAULT 1;"
                )
                await conn.execute(sql)
                logger.info(
                    "SQLite: Column '%s' added to '%s' with DEFAULT 1 (TRUE).",
                    COLUMN_NAME, TABLE_NAME,
                )

    # ── Verify: read back the column list to confirm ───────────────────
    async with engine.begin() as conn:
        if DB_IS_POSTGRES:
            verify_sql = text(
                "SELECT column_name, data_type, column_default "
                "FROM information_schema.columns "
                "WHERE table_name = :tbl AND column_name = :col;"
            )
            result = await conn.execute(verify_sql, {"tbl": TABLE_NAME, "col": COLUMN_NAME})
            row = result.fetchone()
            if row:
                logger.info(
                    "✅ VERIFIED: column='%s' | type='%s' | default='%s'",
                    row[0], row[1], row[2],
                )
            else:
                logger.error(
                    "❌ VERIFICATION FAILED: column '%s' not found in information_schema!",
                    COLUMN_NAME,
                )
                sys.exit(1)
        else:
            pragma_result = await conn.execute(text(f"PRAGMA table_info({TABLE_NAME});"))
            columns = [row[1] for row in pragma_result.fetchall()]
            if COLUMN_NAME in columns:
                logger.info("✅ VERIFIED: column '%s' exists in SQLite table '%s'.", COLUMN_NAME, TABLE_NAME)
            else:
                logger.error("❌ VERIFICATION FAILED: column '%s' missing after ALTER!", COLUMN_NAME)
                sys.exit(1)

    logger.info("Migration complete. All 62 users retain their existing data.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_migration())
