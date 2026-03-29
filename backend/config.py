# ENN - Configuration

from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # LLM Configuration
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_model: str = "MiniMax-M2.7-highspeed"
    llm_base_url: Optional[str] = "https://api.minimax.io/v1/chat/completions"

    # Application
    app_name: str = "ENN"
    debug: bool = True

    # Database
    db_path: str = "/app/data/enn.db"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
