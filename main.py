import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from config import BOT_NAME_RU, BOT_TOKEN, WEB_HOST, WEB_PORT
from database.db import close_db, init_db
from handlers import admin, corruption, personal, proposal, reception, registration, start
from services import admins as admin_service
from services import audit
from utils.throttle import ThrottleMiddleware

logging.basicConfig(level=logging.INFO)


async def run_web(bot: Bot):
    """Сайт запускается в том же процессе и event loop, что и бот (общая БД, мгновенные ответы сотрудникам)."""
    import uvicorn
    from web.app import create_app

    server = uvicorn.Server(uvicorn.Config(
        create_app(bot), host=WEB_HOST, port=WEB_PORT, log_level="warning",
        proxy_headers=False, server_header=False, access_log=False,
    ))
    server.install_signal_handlers = lambda: None   # сигналами управляет основной процесс
    await server.serve()


async def main():
    await init_db()
    generated = await admin_service.seed_admins()
    if generated:
        print("\n" + "=" * 60)
        print("  ПЕРВЫЙ ЗАПУСК: создан веб-аккаунт суперадмина")
        print("  Логин:  admin")
        print(f"  Пароль: {generated}")
        print("  (показан один раз; при первом входе потребуется сменить)")
        print("=" * 60 + "\n")

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    throttle = ThrottleMiddleware()
    dp.message.outer_middleware(throttle)
    dp.callback_query.outer_middleware(throttle)

    @dp.errors()
    async def error_handler(event: ErrorEvent):
        """Логирует неожиданные ошибки и не оставляет кнопку «зависшей»."""
        logging.exception("Ошибка: %s", event.exception)
        update = event.update
        if update.callback_query:
            try:
                await update.callback_query.answer("Произошла ошибка, попробуйте ещё раз.", show_alert=True)
            except Exception:
                pass

    # start.router должен быть первым — «Bekor qilish» работает в любом состоянии.
    dp.include_router(start.router)
    dp.include_router(registration.router)
    dp.include_router(corruption.router)
    dp.include_router(personal.router)
    dp.include_router(proposal.router)
    dp.include_router(reception.router)
    dp.include_router(admin.router)

    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await bot.set_my_name(BOT_NAME_RU, language_code="ru")
        await bot.set_my_description("Обращение бот — платформа Toshkent EM: обращения, предложения и запись на приём.", language_code="ru")
    except Exception as e:
        logging.warning("Не удалось обновить имя бота: %s", e)

    await audit.log(None, "system_start", details="Бот и сайт запущены")
    try:
        await asyncio.gather(dp.start_polling(bot), run_web(bot))
    finally:
        await bot.session.close()
        await close_db()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
