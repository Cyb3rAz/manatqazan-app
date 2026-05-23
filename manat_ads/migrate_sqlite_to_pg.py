"""
ManatAds – SQLite to PostgreSQL Migration Utility
==================================================
This utility copies all existing users and watch records from the local SQLite
database (manat_ads.db) into the production PostgreSQL database.

Usage on VPS:
  docker-compose exec -T app python migrate_sqlite_to_pg.py
"""

import asyncio
import os
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, text
from models import User, WatchRecord
from database import Base

async def migrate():
    sqlite_db_path = Path(__file__).resolve().parent / "manat_ads.db"
    if not sqlite_db_path.exists():
        print(f"❌ SQLite database file not found at: {sqlite_db_path}")
        print("Nothing to migrate.")
        return

    pg_url = os.getenv("DATABASE_URL", "").strip()
    if not pg_url or "postgresql" not in pg_url:
        print("❌ DATABASE_URL environment variable is not configured for PostgreSQL.")
        print("Migration requires a valid PostgreSQL connection string in DATABASE_URL.")
        return

    print("🚀 Starting Database Migration from SQLite to PostgreSQL...")
    print(f"Source: SQLite ({sqlite_db_path.name})")
    print("Destination: PostgreSQL")

    # Create engines
    sqlite_engine = create_async_engine(f"sqlite+aiosqlite:///{sqlite_db_path}", echo=False)
    pg_engine = create_async_engine(pg_url, echo=False)

    sqlite_session_factory = async_sessionmaker(bind=sqlite_engine, expire_on_commit=False)
    pg_session_factory = async_sessionmaker(bind=pg_engine, expire_on_commit=False)

    # 1. Read from SQLite
    async with sqlite_session_factory() as sqlite_session:
        print("\n📥 Fetching data from SQLite...")
        
        # Fetch Users
        users_result = await sqlite_session.execute(select(User).order_by(User.id))
        users = users_result.scalars().all()
        print(f"Found {len(users)} users.")

        # Fetch Watch Records
        records_result = await sqlite_session.execute(select(WatchRecord).order_by(WatchRecord.id))
        records = records_result.scalars().all()
        print(f"Found {len(records)} watch records.")

    if not users:
        print("⚠️ SQLite database is empty. No users to migrate.")
        await sqlite_engine.dispose()
        await pg_engine.dispose()
        return

    # 2. Write to PostgreSQL
    async with pg_session_factory() as pg_session:
        print("\n📤 Migrating to PostgreSQL...")

        # Ensure PG tables are created
        async with pg_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("✅ PostgreSQL tables verified/created.")

        # Check if users already exist in PG to prevent duplicates
        existing_users_result = await pg_session.execute(select(User.id))
        existing_user_ids = set(existing_users_result.scalars().all())

        migrated_users_count = 0
        for u in users:
            if u.id in existing_user_ids:
                print(f"   ⚠️ User ID {u.id} (tg: {u.telegram_id}) already exists in PostgreSQL. Skipping.")
                continue

            # Create a detached instance for PG
            new_user = User(
                id=u.id,
                telegram_id=u.telegram_id,
                username=u.username,
                first_name=u.first_name,
                last_name=u.last_name,
                balance_mc=u.balance_mc,
                total_earned_mc=u.total_earned_mc,
                videos_today=u.videos_today,
                last_watch_date=u.last_watch_date,
                referrer_id=u.referrer_id,
                referral_earnings_mc=u.referral_earnings_mc,
                referral_count=u.referral_count,
                is_active=u.is_active,
                created_at=u.created_at,
                updated_at=u.updated_at
            )
            pg_session.add(new_user)
            migrated_users_count += 1

        await pg_session.flush()
        print(f"✅ Users queued for migration: {migrated_users_count}/{len(users)}")

        # Check if watch records already exist
        existing_records_result = await pg_session.execute(select(WatchRecord.id))
        existing_record_ids = set(existing_records_result.scalars().all())

        migrated_records_count = 0
        for r in records:
            if r.id in existing_record_ids:
                continue

            new_record = WatchRecord(
                id=r.id,
                user_id=r.user_id,
                telegram_id=r.telegram_id,
                reward_mc=r.reward_mc,
                referrer_bonus_mc=r.referrer_bonus_mc,
                referrer_telegram_id=r.referrer_telegram_id,
                adsgram_event_id=r.adsgram_event_id,
                ip_address=r.ip_address,
                watched_at=r.watched_at
            )
            pg_session.add(new_record)
            migrated_records_count += 1

        await pg_session.commit()
        print(f"✅ Watch records migrated: {migrated_records_count}/{len(records)}")

        # 3. Reset PostgreSQL Auto-Increment Sequences
        print("\n🔄 Resetting auto-increment sequences in PostgreSQL...")
        if migrated_users_count > 0:
            await pg_session.execute(text(
                "SELECT setval(pg_get_serial_sequence('users', 'id'), COALESCE(MAX(id), 1)) FROM users;"
            ))
        if migrated_records_count > 0:
            await pg_session.execute(text(
                "SELECT setval(pg_get_serial_sequence('watch_records', 'id'), COALESCE(MAX(id), 1)) FROM watch_records;"
            ))
        await pg_session.commit()
        print("✅ Sequences successfully reset.")

    print("\n🎉 Migration completed successfully!")

    # Dispose engines
    await sqlite_engine.dispose()
    await pg_engine.dispose()

if __name__ == "__main__":
    asyncio.run(migrate())
