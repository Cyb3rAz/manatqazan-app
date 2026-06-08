import asyncio
import os
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()

from database import engine

async def run_fix():
    print("Starting production database fix for balances and loyalty bonus...")
    try:
        async with engine.begin() as conn:
            # 1. Ensure the loyalty_bonus_claimed column exists and is BOOLEAN
            print("Ensuring loyalty_bonus_claimed column exists...")
            try:
                await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS loyalty_bonus_claimed BOOLEAN DEFAULT FALSE;"))
            except Exception as e:
                if 'duplicate column name' in str(e).lower() or 'already exists' in str(e).lower():
                    print("Column already exists.")
                else:
                    raise e
            
            # 2. Find legacy users who got the 4.0 AZN injected via add_welcome_bonus.py
            #    but haven't officially claimed it through the WebApp yet.
            #    We roll back the 4.0 AZN so their balance drops, and they get the popup in the WebApp.
            print("Rolling back the 4.0 AZN for users who haven't claimed it via WebApp yet...")
            rollback_sql = text("""
                UPDATE users 
                SET balance_mc = balance_mc - 4.0, loyalty_bonus_claimed = FALSE
                WHERE (balance_mc - total_earned_mc) >= 3.0 
                  AND loyalty_bonus_claimed = FALSE;
            """)
            res = await conn.execute(rollback_sql)
            print(f"Fixed: Rolled back 4.0 AZN for {res.rowcount} legacy users. They will now see the popup in the WebApp.")
            
    except Exception as e:
        print(f"Error during fix: {e}")
    finally:
        await engine.dispose()
        print("Database fix complete!")

if __name__ == '__main__':
    asyncio.run(run_fix())
