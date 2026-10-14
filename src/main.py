import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import config
from bot.handlers import router


async def main() -> None:
    bot = Bot(token=config.bot_token)
    dp = Dispatcher()
    dp.include_router(router)

    logging.info("yoink starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())