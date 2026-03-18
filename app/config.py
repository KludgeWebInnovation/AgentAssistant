from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    base_dir: Path
    data_dir: Path
    database_url: str
    admin_username: str
    admin_password: str
    session_secret: str
    openai_api_key: str
    openai_research_model: str
    openai_classify_model: str


@lru_cache
def get_settings() -> Settings:
    base_dir = Path(__file__).resolve().parent.parent
    load_dotenv(base_dir / ".env")
    data_dir = base_dir / "data"
    default_db = f"sqlite:///{(data_dir / 'aisdr.db').resolve().as_posix()}"
    return Settings(
        app_name=os.getenv("APP_NAME", "AISDR"),
        app_env=os.getenv("APP_ENV", "development"),
        base_dir=base_dir,
        data_dir=data_dir,
        database_url=os.getenv("DATABASE_URL", default_db),
        admin_username=os.getenv("ADMIN_USERNAME", "admin"),
        admin_password=os.getenv("ADMIN_PASSWORD", "change-me"),
        session_secret=os.getenv("SESSION_SECRET", "development-secret-key"),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_research_model=os.getenv("OPENAI_RESEARCH_MODEL", "gpt-4.1-mini"),
        openai_classify_model=os.getenv("OPENAI_CLASSIFY_MODEL", "gpt-4.1-mini"),
    )
