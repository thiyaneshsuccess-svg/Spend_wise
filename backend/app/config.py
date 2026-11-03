"""Application settings, loaded from the environment.

Configuration lives in one object so that nothing in the codebase reaches for
``os.environ`` directly. That keeps tests able to override values by
constructing ``Settings(...)`` instead of mutating global state.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BACKEND_DIR / "spendwise.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_prefix="SPENDWISE_",
        extra="ignore",
    )

    database_url: str = f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"
    currency: str = "INR"
    timezone: str = "Asia/Kolkata"

    # Enables the demo-data endpoint. Local development only; a hosted demo
    # would flip this off or require auth before seeding.
    demo_mode: bool = True

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
