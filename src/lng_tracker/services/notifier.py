from aiogram import Bot
from loguru import logger

from lng_tracker.repository.users import UserRepository


class TelegramNotifier:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.users_repository = UserRepository()

    async def send_vessel_alert(self, vessel_name: str, zone: str, mmsi: str):
        allowed_user = await self.users_repository.get_allowed_users()

        if not allowed_user:
            logger.warning("Skipping alert: no allowed users in whitelist")
            return

        logger.info(
            "Sending vessel alert | vessel={} | mmsi={} | zone={} | recipients={}",
            vessel_name,
            mmsi,
            zone,
            len(allowed_user),
        )

        text = (
            f"🚢 <b>LNG: ВХОД В ЗОНУ</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📍 <b>Локация:</b> {zone}\n"
            f"🚢 <b>Судно:</b> <code>{vessel_name}</code>\n"
            f"🆔 <b>MMSI:</b> <code>{mmsi}</code>"
        )
        delivered = 0
        for user in allowed_user:
            try:
                await self.bot.send_message(
                    chat_id=user.telegram_id,
                    text=text,
                    parse_mode="HTML",
                )
                delivered += 1
            except Exception as exc:
                logger.error("Error sending to user {}: {}", user.telegram_id, exc)

        logger.info("Alert delivery completed: {}/{}", delivered, len(allowed_user))
