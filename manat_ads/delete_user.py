"""
ManatAds – Delete User Utility
=================================
Deletes a user by Telegram ID from the configured database (PostgreSQL or SQLite).

Usage on VPS:
  docker-compose exec -i app python delete_user.py <telegram_id>
or:
  python delete_user.py <telegram_id>
"""

import asyncio
import sys
from sqlalchemy import delete, select
from database import async_session, engine
from models import User

async def delete_user(telegram_id: int):
    print(f"Connecting to database (dialect: {engine.dialect.name})...")
    async with async_session() as session:
        # Check if user exists
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        
        if not user:
            print(f"❌ User with Telegram ID {telegram_id} not found in the database.")
            return

        username_str = f" (@{user.username})" if user.username else ""
        print(f"Found user: {user.first_name or 'N/A'}{username_str} | ID: {user.id}")
        
        # Perform deletion (cascades to watch_records)
        await session.execute(delete(User).where(User.telegram_id == telegram_id))
        await session.commit()
        print(f"✅ Successfully deleted user {telegram_id} and all related records.")

async def main():
    if len(sys.argv) < 2:
        print("Usage: python delete_user.py <telegram_id>")
        sys.exit(1)
        
    try:
        telegram_id = int(sys.argv[1])
    except ValueError:
        print("Error: Telegram ID must be an integer.")
        sys.exit(1)
        
    await delete_user(telegram_id)
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
