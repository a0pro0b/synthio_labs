from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    provider: Literal["azure", "openai"] = Field("azure", validation_alias="REALTIME_PROVIDER")

    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_realtime_deployment: str = Field(
        "gpt-realtime", validation_alias="AZURE_OPENAI_REALTIME_DEPLOYMENT"
    )

    openai_api_key: str = ""
    openai_realtime_model: str = "gpt-realtime-2.1"

    voice: str = Field("ash", validation_alias="REALTIME_VOICE")
    voice_speed: float = Field(1.15, ge=0.25, le=1.5, validation_alias="REALTIME_SPEED")
    transcribe_model: str = "gpt-4o-transcribe"
    vad_eagerness: Literal["auto", "low", "medium", "high"] = "auto"
    agent_mode: Literal["multi", "single"] = "multi"
    grounding_guardrail: bool = True

    allowed_origins: str = ""
    storage_dir: Path = BACKEND_DIR / "storage" / "decks"
    frontend_dist: Path = REPO_ROOT / "frontend" / "dist"
    max_upload_mb: int = 25
    max_slides: int = 40
    soffice_timeout_s: int = 60

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    def missing_credentials(self) -> list[str]:
        """Env vars that must be set before a realtime session can start."""
        if self.provider == "azure":
            required = {
                "AZURE_OPENAI_ENDPOINT": self.azure_openai_endpoint,
                "AZURE_OPENAI_API_KEY": self.azure_openai_api_key,
                "AZURE_OPENAI_REALTIME_DEPLOYMENT": self.azure_realtime_deployment,
            }
        else:
            required = {"OPENAI_API_KEY": self.openai_api_key}
        return [name for name, value in required.items() if not value]


@lru_cache
def get_settings() -> Settings:
    return Settings()
