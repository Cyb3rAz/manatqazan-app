import asyncio
import sys
from database import async_session, close_db
from models import User
from sqlalchemy import select

async def main():
    if len(sys.argv) < 2:
        telegram_id = 6469663868
    else:
        try:
            telegram_id = int(sys.argv[1])
        except ValueError:
            print("Please provide a valid integer Telegram ID.")
            return

    print(f"Attempting to delete user with telegram_id: {telegram_id}...")

    async with async_session() as session:
        async with session.begin():
            stmt = select(User).where(User.telegram_id == telegram_id)
            res = await session.execute(stmt)
            user = res.scalar_one_or_none()
            if user:
                await session.delete(user)
                print(f"Success: User {telegram_id} (ID: {user.id}) has been deleted from the database.")
            else:
                print(f"Info: User {telegram_id} not found in the database.")
                
    await close_db()

if __name__ == "__main__":
    asyncio.run(main())
