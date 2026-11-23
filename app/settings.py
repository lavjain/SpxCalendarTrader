"""Environment-driven settings: keys, callback, token path, database path, feature flags.

Trading numbers live in app/core/config.py, not here. Values come from the environment
(`uv run --env-file .env ...` or `serve`, which loads .env) and fall back to .env in the working dir.
"""
from functools import lru_cache
from importlib import metadata

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core import config


def app_version() -> str:
    try:
        return metadata.version("spx-calendar-trader")
    except metadata.PackageNotFoundError:
        return "0.1.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    schwab_app_key: str = ""
    schwab_app_secret: str = ""
    schwab_callback_url: str = "https://127.0.0.1:8182"
    schwab_token_path: str = "~/.schwab/calendar_skew_token.json"
    db_path: str = config.DB_PATH
    snapshot_path: str = config.SNAPSHOT_PATH   # the one JSON file holding the saved Finder snapshots
    feature_analyzer: bool = False          # shows the Analyzer tab (Application Phase 2)


@lru_cache
def get_settings() -> Settings:
    return Settings()
