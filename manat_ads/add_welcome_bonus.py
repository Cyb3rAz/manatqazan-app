import asyncio
import os
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()

from database import engine

async def run_bonus_patch():
    print("Connecting to Production Database to add 4.0 AZN Welcome Bonus...")
    try:
        async with engine.begin() as conn:
            # We add 4.0 AZN to balance_mc for existing legacy users.
            # A good way to identify them is that they don't have the 4.0 difference 
            # between balance_mc and total_earned_mc (which new users get automatically),
            # or simply they were created before this update.
            # To be safe, we will just add 4.0 AZN to balance_mc for users where 
            # (balance_mc - total_earned_mc) < 3.0 (meaning they definitely haven't received the 4 AZN base).
            
            bonus_sql = text("""
                UPDATE users 
                SET balance_mc = balance_mc + 4.0
                WHERE (balance_mc - total_earned_mc) < 3.0;
            """)
            
            res = await conn.execute(bonus_sql)
            print(f"Successfully added 4.0 AZN welcome bonus to {res.rowcount} users!")
            
    except Exception as e:
        print(f"Error executing bonus patch: {e}")
    finally:
        await engine.dispose()
        print("Process complete!")

if __name__ == '__main__':
    asyncio.run(run_bonus_patch())
