import asyncio
from sqlalchemy import text
from database import engine

async def delete_user():
    async with engine.begin() as conn:
        res = await conn.execute(text('DELETE FROM users WHERE telegram_id = 5652985553'))
        print(f'Sildiyimiz istifadəçi sayı: {res.rowcount}')
    await engine.dispose()
    print('İstifadəçi 5652985553 uğurla silindi!')

if __name__ == "__main__":
    asyncio.run(delete_user())
