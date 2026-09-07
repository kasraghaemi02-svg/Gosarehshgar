from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    bot_token: str
    super_admin_id: int
    db_path: str
    timezone: str

    vertex_service_account_json: str | None
    vertex_project_id: str | None
    vertex_location: str
    vertex_model: str

    melipayamak_username: str
    melipayamak_password: str
    melipayamak_api_url: str
    sms_templates: dict[str, str]


def load_config() -> Config:
    load_dotenv()

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("BOT_TOKEN is not set. Create .env from .env.example")

    super_admin_id_raw = os.getenv("SUPER_ADMIN_ID", "").strip()
    if not super_admin_id_raw:
        raise RuntimeError("SUPER_ADMIN_ID is not set")

    return Config(
        bot_token=bot_token,
        super_admin_id=int(super_admin_id_raw),
        db_path=os.getenv("DB_PATH", "Database_asli.db").strip(),
        timezone=os.getenv("TIMEZONE", "Asia/Tehran").strip(),
        vertex_service_account_json=os.getenv("VERTEX_SERVICE_ACCOUNT_JSON", "").strip() or None,
        vertex_project_id=os.getenv("VERTEX_PROJECT_ID", "").strip() or None,
        vertex_location=os.getenv("VERTEX_LOCATION", "us-central1").strip(),
        vertex_model=os.getenv("VERTEX_MODEL", "gemini-1.5-flash").strip(),
        melipayamak_username=os.getenv("MELIPAYAMAK_USERNAME", "19128193953").strip(),
        melipayamak_password=os.getenv("MELIPAYAMAK_PASSWORD", "3B@#R").strip(),
        melipayamak_api_url="https://api.payamak-panel.com/post/Send.asmx?wsdl",
        sms_templates={
            "interview_24h": "ایران آوسبیلدونگ | یادآوری مصاحبه\n\nبا سلام،\nوقت مصاحبه برای پرونده {client_name} فردا مورخ {date} ساعت {time} برنامه‌ریزی شده است.\n\nلطفاً در زمان مقرر برای انجام مصاحبه آنلاین حضور داشته باشید.\n\nبا احترام\nایران آوسبیلدونگ",
            "interview_2h": "ایران آوسبیلدونگ | یادآوری فوری مصاحبه\n\nبا سلام،\nوقت مصاحبه 2 ساعت دیگر ساعت {time} برای پرونده {client_name} خواهد بود.\n\nلطفاً در زمان مقرر برای انجام مصاحبه آنلاین حضور داشته باشید.\n\nآمادگی لازم را فرمایید.\n\nبا احترام\nایران آوسبیلدونگ",
        }
    )
