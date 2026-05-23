"""
ManatAds – Database Schema Migration (v2)
===========================================
Safely adds sequential session columns to the 'users' table if they do not already exist.
Compatible with both PostgreSQL and SQLite.
"""

import asyncio
import logging
from sqlalchemy import text
from database import engine, DB_IS_POSTGRES, close_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("manatads.migration")

async def run_migration():
    logger.info("Starting schema migration v2...")
    logger.info("Target Database is PostgreSQL: %s", DB_IS_POSTGRES)

    async with engine.begin() as conn:
        # Check existing columns in 'users' table
        if DB_IS_POSTGRES:
            # PostgreSQL column check query
            check_query = text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'users';"
            )
            result = await conn.execute(check_query)
            existing_columns = {row[0] for row in result.fetchall()}
        else:
            # SQLite column check query
            result = await conn.execute(text("PRAGMA table_info(users);"))
            existing_columns = {row[1] for row in result.fetchall()}

        logger.info("Existing columns in 'users' table: %s", existing_columns)

        # Columns to add
        columns_to_add = [
            ("session_1_count", "INTEGER DEFAULT 0"),
            ("session_2_count", "INTEGER DEFAULT 0"),
            ("session_1_completion_time", "TIMESTAMP WITH TIME ZONE" if DB_IS_POSTGRES else "DATETIME"),
        ]

        for col_name, col_type in columns_to_add:
            if col_name not in existing_columns:
                logger.info("Adding column '%s' (%s) to 'users' table...", col_name, col_type)
                alter_query = text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type};")
                await conn.execute(alter_query)
                logger.info("Column '%s' added successfully.", col_name)
            else:
                logger.info("Column '%s' already exists. Skipping.", col_name)

    logger.info("Migration v2 completed successfully!")

if __name__ == "__main__":
    try:
        asyncio.run(run_migration())
    finally:
        asyncio.run(close_db())
