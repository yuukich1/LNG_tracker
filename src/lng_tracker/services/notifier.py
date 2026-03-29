import csv
import os
from datetime import datetime

from aiogram import Bot
from aiogram.types import FSInputFile
from loguru import logger

from lng_tracker.core.config import settings
from lng_tracker.repository.users import UserRepository
from lng_tracker.repository.vessels import VesselRepository


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

    async def send_daily_report(self):
        now = datetime.now()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        daily_records = await self.vessels_repository.get_history_report_rows(since=day_start)

        reports_dir = os.path.join(os.getcwd(), "data", "reports")
        os.makedirs(reports_dir, exist_ok=True)

        if not daily_records:
            logger.info("No daily events found for report")
            return

        daily_filename = f"lng_report_{now.strftime('%d_%m_%Y')}.csv"
        daily_file_path = os.path.join(reports_dir, daily_filename)
        self._write_daily_report(daily_file_path, daily_records)

        await self.bot.send_document(
            chat_id=settings.chat_id,
            document=FSInputFile(daily_file_path),
            caption=(
                f"<b>Daily report</b>\n"
                f"Events today: {len(daily_records)}"
            ),
            parse_mode="HTML",
        )

    def _write_daily_report(self, file_path: str, records):
        with open(file_path, mode="w", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file, delimiter=";")
            writer.writerow(["Vessel", "Zone", "Event", "Time", "Time In Zone"])
            for record in records:
                writer.writerow([
                    record.name,
                    record.zone,
                    record.event_type,
                    record.dt.strftime("%H:%M:%S"),
                    record.time_in_zone,
                ])
