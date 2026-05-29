import asyncio
from aiogram import types as aio_types
from bot_instance import bot
from handlers.commands import ADMIN_IDS

async def main():
    admin_commands = [
        aio_types.BotCommand(command="start", description="Botu başlat ve Yenile"),
        aio_types.BotCommand(command="lang", description="Dil seçimini dəyiş"),
        aio_types.BotCommand(command="admin", description="Admin panelini aç")
    ]
    for admin_id in ADMIN_IDS:
        try:
            await bot.set_my_commands(
                commands=admin_commands,
                scope=aio_types.BotCommandScopeChat(chat_id=admin_id)
            )
            print(f"Commands successfully set for {admin_id}")
        except Exception as e:
            print(f"Failed for {admin_id}: {e}")
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
