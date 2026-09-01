from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Inseg Psicossocial"
    secret_key: str = "change-me-inseg-psicossocial-dev-secret"
    access_token_expire_minutes: int = 60 * 12
    database_url: str = "sqlite:///./psicossocial.db"
    data_dir: str = "./data"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    bootstrap_admin_email: str = "admin@inseg.local"
    bootstrap_admin_password: str = "inseg123"
    bootstrap_admin_name: str = "Admin Inseg"
    openrouter_api_key: str = ""
    openrouter_model: str = "google/gemini-2.5-flash"
    openrouter_orchestrator_model: str = "google/gemini-2.5-flash"
    openrouter_chat_model: str = "google/gemini-2.5-flash"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def export_llm_env() -> None:
    """Garante que o motor leia a chave via os.environ."""
    import os

    s = get_settings()
    if s.openrouter_api_key:
        os.environ["OPENROUTER_API_KEY"] = s.openrouter_api_key
    model = (s.openrouter_model or "").strip()
    if model and "/" not in model:
        # OpenRouter exige prefixo do provedor
        model = f"openai/{model}"
    if model:
        os.environ["OPENROUTER_MODEL"] = model
    orch = (s.openrouter_orchestrator_model or "").strip()
    if orch and "/" not in orch:
        orch = f"openai/{orch}"
    if orch:
        os.environ["OPENROUTER_ORCHESTRATOR_MODEL"] = orch
    chat = (s.openrouter_chat_model or "").strip()
    if chat and "/" not in chat:
        chat = f"openai/{chat}"
    if chat:
        os.environ["OPENROUTER_CHAT_MODEL"] = chat
