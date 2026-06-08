import asyncio
from sqlalchemy import text
from database import engine

async def run_rollback():
    print("Starting rollback and flag migration...")
    try:
        async with engine.begin() as conn:
            # 1. Add the column (catch exception if it already exists)
            print("Adding loyalty_bonus_claimed column...")
            try:
                await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS loyalty_bonus_claimed BOOLEAN DEFAULT FALSE;"))
            except Exception as e:
                if 'duplicate column name' in str(e).lower():
                    print("Column already exists, skipping addition.")
                else:
                    raise e

            # 2. Rollback the hard injection for users who already received it.
            # Only target legacy users who got the 4.0 AZN injection (balance_mc - total_earned_mc >= 3.0)
            rollback_sql = text("""
                UPDATE users 
                SET balance_mc = balance_mc - 4.0, loyalty_bonus_claimed = 0
                WHERE (balance_mc - total_earned_mc) >= 3.0;
            """)
            res = await conn.execute(rollback_sql)
            print(f"Rolled back 4.0 AZN for {res.rowcount} legacy users and flagged them to claim via WebApp.")
            
    except Exception as e:
        print(f"Error during rollback: {e}")
    finally:
        await engine.dispose()
        print("Migration complete!")

if __name__ == '__main__':
    asyncio.run(run_rollback())
