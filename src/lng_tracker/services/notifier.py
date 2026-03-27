import csv
from datetime import datetime
import io
import os

from aiogram import Bot
from aiogram.types import BufferedInputFile, FSInputFile
from loguru import logger

from lng_tracker.repository.users import UserRepository
from lng_tracker.repository.vessels import VesselRepository
from lng_tracker.core.config import settings

class TelegramNotifier:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.users_repository = UserRepository()
        self.vessels_repository = VesselRepository()

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


    async def send_daily_csv_report(self):
        records = await self.vessels_repository.get_history()
        if not records:
            return
        reports_dir = os.path.join(os.getcwd(), "data", "reports")
        os.makedirs(reports_dir, exist_ok=True)

        filename = f"lng_report_{datetime.now().strftime('%d_%m_%Y')}.csv"
        file_path = os.path.join(reports_dir, filename)

        with open(file_path, mode='w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(['Vessel', 'Zone', 'Event', 'Time'])
            for r in records:
                writer.writerow([
                    r.name, 
                    r.zone, 
                    r.event_type, 
                    r.dt.strftime('%H:%M:%S')
                ])

        await self.bot.send_document(
            chat_id=settings.chat_id,
            document=FSInputFile(file_path),
            caption=(
                f"📈 <b>Автоматический отчет</b>\n"
                f"Событий за сутки: {len(records)}\n"
                f"📁 Файл сохранен на сервере"
            ),
            parse_mode='HTML'
        )