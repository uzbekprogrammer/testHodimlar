import asyncio
import logging

from aiogram.exceptions import TelegramRetryAfter

from utils import roles

log = logging.getLogger(__name__)


async def safe_send(bot, chat_id: int, text: str, **kwargs) -> bool:
    """Отправка с одной повторной попыткой при flood-лимите. Ошибки не прерывают вызывающего."""
    for attempt in (1, 2):
        try:
            await bot.send_message(chat_id, text, **kwargs)
            return True
        except TelegramRetryAfter as e:
            if attempt == 2:
                return False
            await asyncio.sleep(e.retry_after + 0.5)
        except Exception as e:  # заблокировал бота, чат не найден и т.п.
            log.warning("Не удалось отправить сообщение %s: %s", chat_id, e)
            return False
    return False


async def notify_roles(bot, text: str, *role_names: str, **kwargs):
    ids = roles.ids_with_role(*role_names)
    await asyncio.gather(*(safe_send(bot, uid, text, **kwargs) for uid in ids))


async def notify_superadmins(bot, text: str):
    """Сообщает всем суперадминистраторам о важном действии."""
    await notify_roles(bot, text, roles.ROLE_SUPERADMIN)


async def notify_director(bot, text: str):
    await notify_roles(bot, text, roles.ROLE_DIRECTOR)
