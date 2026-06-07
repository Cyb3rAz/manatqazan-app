import asyncio
import os
from sqlalchemy import select, text
from dotenv import load_dotenv

load_dotenv()

# Optionally override environment variables here if needed
# os.environ["DATABASE_URL"] = "postgresql+asyncpg://user:password@localhost/dbname"

from database import engine

async def run_patch():
    print("Connecting to Production Database...")
    try:
        async with engine.begin() as conn:
            print("Executing VC unit collision mathematical fix...")
            
            # 1. Fix balance_mc
            fix_balance_sql = text("""
                UPDATE users 
                SET balance_mc = (FLOOR(balance_mc) / 140000.0) + (balance_mc - FLOOR(balance_mc))
                WHERE balance_mc > 50;
            """)
            res1 = await conn.execute(fix_balance_sql)
            print(f"Updated balance_mc for {res1.rowcount} users.")
            
            # 2. Fix total_earned_mc
            fix_total_sql = text("""
                UPDATE users 
                SET total_earned_mc = (FLOOR(total_earned_mc) / 140000.0) + (total_earned_mc - FLOOR(total_earned_mc))
                WHERE total_earned_mc > 50;
            """)
            res2 = await conn.execute(fix_total_sql)
            print(f"Updated total_earned_mc for {res2.rowcount} users.")
            
            # 3. Fix referral_earnings_mc
            fix_ref_sql = text("""
                UPDATE users 
                SET referral_earnings_mc = (FLOOR(referral_earnings_mc) / 140000.0) + (referral_earnings_mc - FLOOR(referral_earnings_mc))
                WHERE referral_earnings_mc > 50;
            """)
            res3 = await conn.execute(fix_ref_sql)
            print(f"Updated referral_earnings_mc for {res3.rowcount} users.")
            
    except Exception as e:
        print(f"Error executing migration: {e}")
    finally:
        await engine.dispose()
        print("Migration complete!")

if __name__ == '__main__':
    asyncio.run(run_patch())
