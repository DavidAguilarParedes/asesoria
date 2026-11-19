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
    agent_reasoning_effort: str = "low"
    # Puntaje mínimo del reranker para considerar que hay evidencia
    rag_min_score: float = -2.0
    # Si el agente busca en la colección con contexto por chunk (Contextual Retrieval)
    agent_contextual: bool = False

    alpaca_api_key: SecretStr | None = None
    alpaca_secret_key: SecretStr | None = None
    alpaca_paper_trade: bool = True
    # La API abre el MCP de Alpaca al arrancar; en false responde sin acceso al mercado
    api_use_mcp: bool = True

    # MLflow (opcional): trazas de cada conversación y registro de las evaluaciones
    mlflow_tracking_uri: str | None = None
    # Dirección de MLflow para el navegador (en Docker difiere de la interna)
    mlflow_ui_url: str = "http://localhost:5000"

    # La SEC pide un User-Agent con nombre y correo de contacto
    sec_user_agent: str = "asesoria-demo"

    qdrant_path: Path = Path(".qdrant")
    # Si se define, se usa un servidor Qdrant (Docker) en vez de la carpeta local
    qdrant_url: str | None = None
    collection: str = "asesoria"
    data_dir: Path = Path("data")


def get_settings() -> Settings:
    return Settings()
