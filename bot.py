import asyncio
import logging
import os
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN
from handlers import router

logging.basicConfig(level=logging.INFO)


async def health_check(request):
    """Простой эндпоинт для Render — показывает, что бот жив."""
    return web.Response(text="OK — bot is running 🚀")


async def run_web_server():
    """Запускает HTTP-сервер на порту, который требует Render."""
    app = web.Application()
    app.router.add_get("/", health_check)
    
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"🌐 Web server started on port {port}")
    
    # Держим сервер живым бесконечно
    while True:
        await asyncio.sleep(3600)


async def main():
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)

    # Запускаем параллельно: бот + веб-сервер
    await asyncio.gather(
        dp.start_polling(bot),
        run_web_server(),
    )


if __name__ == "__main__":
    asyncio.run(main())