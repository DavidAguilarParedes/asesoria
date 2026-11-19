from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: str = "openai"
    openai_api_key: SecretStr | None = None
    openai_chat_model: str = "gpt-5-mini"
    openai_fast_model: str = "gpt-5-nano"
    openai_embedding_model: str = "text-embedding-3-small"
    max_usd_per_run: float = 0.30

    alpaca_api_key: SecretStr | None = None
    alpaca_secret_key: SecretStr | None = None
    alpaca_paper_trade: bool = True

    # La SEC pide un User-Agent con nombre y correo de contacto
    sec_user_agent: str = "asesoria-demo"

    qdrant_path: Path = Path(".qdrant")
    collection: str = "asesoria"
    data_dir: Path = Path("data")


def get_settings() -> Settings:
    return Settings()
