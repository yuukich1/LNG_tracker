from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message
from sqlalchemy import select
from lng_tracker.database.connect import async_session_maker
from lng_tracker.database.models import Users
from loguru import logger

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
        async with async_session_maker() as session:
            stmt = select(Users).where(Users.telegram_id == event.from_user.id) # type: ignore
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            if not user or not user.is_allowed:
                
                logger.warning(f"Access denied for user {event.from_user.id} (@{event.from_user.username})") # type: ignore
                await event.answer(
                    "🚫 <b>Доступ ограничен.</b>\n\n"
                    f"Вашего ID нет в белом списке.\n"
                    f"Обратитесь к <b>@ultimap</b> для подтверждения.\n\n"
                    f"🔑 Ваш ID: <code>{event.from_user.id}</code>", # type: ignore
                    parse_mode="HTML"
                )
                return  
        return await handler(event, data)