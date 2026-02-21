"""Application configuration via pydantic-settings."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "TasteBud"
    debug: bool = False

    # Storage
    download_dir: Path = _PROJECT_ROOT / "downloads"

    # Sieve thresholds
    sieve_layer1_threshold: float = 0.3
    sieve_layer2_threshold: float = 0.2

    # CLIP (Layer 1 — optional, graceful fallback if not installed)
    clip_model: str = "clip-ViT-B-32"

    # Ollama VLM (Layer 2)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "moondream"


settings = Settings()
