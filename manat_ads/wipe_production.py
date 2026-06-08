import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# Override the database URL with the production PostgreSQL URL
# Ensure this matches the `postgresql+asyncpg://...` connection string used in docker-compose.yml
DB_URL = os.environ.get(
    "DATABASE_URL", 
    "postgresql+asyncpg://manatads:changeme_in_production@localhost:5432/manat_ads"
)

# Important: Use asyncpg engine for async execution
engine = create_async_engine(DB_URL, echo=True)

async def wipe_exploiters():
    print(f"Connecting to production DB: {DB_URL.replace('//manatads:', '//manatads:***@')}")
    try:
        async with engine.begin() as conn:
            # Revert exploiters' balances back to the baseline limit
            res = await conn.execute(
                text('UPDATE users SET balance_mc = 4.0, total_earned_mc = 4.0 WHERE balance_mc > 15.0')
            )
            print(f"Wiped exploiter count in Production DB: {res.rowcount}")
            
        print("All bugged accounts in Production successfully lowered to 4.0 MC!")
    except Exception as e:
        print(f"Failed to execute wipe on Production DB: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(wipe_exploiters())
