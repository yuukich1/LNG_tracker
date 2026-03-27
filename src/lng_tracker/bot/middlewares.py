from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from loguru import logger

from lng_tracker.repository.users import UserRepository

user_repository = UserRepository()


class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        if event.text and event.text.startswith("/start"):
            return await handler(event, data)

        user = await user_repository.get_by_telegram_id(event.from_user.id)  # type: ignore[arg-type]
        if not user or not user.is_allowed:
            logger.warning(f"Access denied for user {event.from_user.id} (@{event.from_user.username})")  # type: ignore
            await event.answer(
                "🚫 <b>Доступ ограничен.</b>\n\n"
                f"Вашего ID нет в белом списке.\n"
                f"Обратитесь к <b>@ultimap</b> для подтверждения.\n\n"
                f"🔑 Ваш ID: <code>{event.from_user.id}</code>",  # type: ignore
                parse_mode="HTML"
            )
            return

        return await handler(event, data)
