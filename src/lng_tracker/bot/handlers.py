from datetime import datetime, timedelta

from aiogram import Bot, Router, types
from aiogram.filters import Command, CommandObject
from loguru import logger

from lng_tracker.core.config import settings
from lng_tracker.repository.users import UserRepository
from lng_tracker.repository.vessels import VesselRepository

router = Router()
user_repository = UserRepository()
vessel_repository = VesselRepository()


@router.message(Command("start"))
async def cmd_start(message: types.Message, bot: Bot):
    try:
        admin_info = await bot.get_chat(settings.chat_id)
        admin_username = f"@{admin_info.username}" if admin_info.username else "администратору"
    except Exception:
        admin_username = "администратору"

    await user_repository.save_user(
        telegram_id=message.from_user.id,  # type: ignore[arg-type]
        username=message.from_user.username,  # type: ignore[arg-type]
        is_allowed=False,
    )
    try:
        await bot.send_message(
            chat_id=settings.chat_id,
            text=f"🔔 <b>Новая заявка!</b>\nЮзер: @{message.from_user.username or 'hidden'}\n"  # type: ignore
                 f"ID: <code>{message.from_user.id}</code>\n"  # type: ignore
                 f"Разрешить: <code>/approve {message.from_user.id}</code>",  # type: ignore
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка уведомления админа: {e}")

    await message.answer(
        "👋 <b>Добро пожаловать в LNG Tracker!</b>\n\n"
        f"Ваш ID зарегистрирован. Для получения доступа напишите <b>{admin_username}</b>.\n\n"
        f"🔑 Ваш ID: <code>{message.from_user.id}</code>",  # type: ignore
        parse_mode="HTML"
    )


@router.message(Command("status"))
async def cmd_status(message: types.Message):
    vessels = await vessel_repository.get_active_vessels()

    if not vessels:
        await message.answer("⏸ В данный момент в зонах LNG-танкеров не обнаружено.")
        return

    text = "🚢 <b>Текущая обстановка в зонах:</b>\n"
    text += "━━━━━━━━━━━━━━━\n"
    for vessel in vessels:
        text += f"📍 <b>{vessel.zone}</b>: <code>{vessel.name}</code>\n"

    await message.answer(text, parse_mode="HTML")


@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    day_ago = datetime.now() - timedelta(days=1)
    count = await vessel_repository.count_entries_since(day_ago)

    await message.answer(
        f"📊 <b>Статистика за 24 часа:</b>\n"
        f"Зафиксировано <b>{count}</b> входов танкеров в зоны.",
        parse_mode="HTML"
    )


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    text = (
        "📖 <b>Доступные команды:</b>\n\n"
        "/status — Кто в проливах прямо сейчас\n"
        "/stats — Активность за последние 24 часа\n"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("approve"))
async def cmd_approve(message: types.Message, command: CommandObject):
    if message.from_user.id != settings.chat_id:  # type: ignore
        return

    if not command.args:
        await message.answer("Введите ID: <code>/approve 12345</code>")
        return

    try:
        target_id = int(command.args)
        await user_repository.approve_user(target_id)
        await message.answer(f"✅ Доступ для <code>{target_id}</code> разрешен.", parse_mode="HTML")
    except ValueError:
        await message.answer("ID должен быть числом.")


@router.message(Command("clear_db"))
async def cmd_clear_db(message: types.Message):
    if message.from_user.id != settings.chat_id:  # type: ignore
        await message.answer("❌ У вас нет прав.")
        return

    try:
        await vessel_repository.clear_tracking_data()
        await message.answer("🗑 <b>База данных очищена.</b>", parse_mode="HTML")
        logger.warning(f"Admin {message.from_user.id} cleared DB.")  # type: ignore
    except Exception as e:
        await message.answer(f"⚠️ Ошибка: {e}")
