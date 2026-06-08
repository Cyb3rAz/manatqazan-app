import asyncio
from sqlalchemy import text
from database import engine

async def wipe_bugged():
    async with engine.begin() as conn:
        res = await conn.execute(text('UPDATE users SET balance_mc = 0, total_earned_mc = 0 WHERE balance_mc >= 49.0 OR total_earned_mc >= 49.0'))
        print(f'Sıfırlanan buglu istifadəçi sayı: {res.rowcount}')
    await engine.dispose()
    print('Böyük buglu hesablar uğurla təmizləndi!')

if __name__ == "__main__":
    asyncio.run(wipe_bugged())
