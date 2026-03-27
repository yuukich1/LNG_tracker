from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    telegram_token: str = 'your_telegram_token'
    database_url: str = "sqlite+aiosqlite:///data/monitor.db"
    MONITOR_ZONES: dict[str, List[float]] = {
        "Panama Canal": [8.43951, 9.90122, -80.31006, -78.92303],
        "Suez Canal": [29.45873, 32.99917, 31.82739, 33.58521],
        "Gibraltar": [34.65129, 36.51405, -6.87744, -4.30115],
        "Bab el-Mandeb": [11.46387, 13.74739, 42.49512, 44.82422],
        "Strait of Hormuz": [26.29342, 27.34249, 55.42877, 57.54364],
        "Strait of Malacca": [0.49438, 3.42569, 99.71191, 105.02930],
    }
    scan_interval: int = 600
    chat_id: int = 0
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()