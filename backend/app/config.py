from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    dashscope_api_key: str | None = None
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_text_model: str = "qwen-plus"
    llm_connect_timeout_seconds: float = 5.0
    llm_total_timeout_seconds: float = 30.0
    llm_max_concurrency: int = 4
    llm_max_retries: int = 2


settings = Settings()
