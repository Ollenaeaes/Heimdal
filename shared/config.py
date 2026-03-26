"""Platform configuration loader.

Reads environment variables via pydantic-settings and merges with config.yaml.
Singleton: ``from shared.config import settings``
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings


# ---------------------------------------------------------------------------
# Nested config sections (loaded from YAML, overridable via env)
# ---------------------------------------------------------------------------

class ScoringDebounceConfig(BaseSettings):
    default_seconds: float = 60.0
    red_tier_seconds: float = 30.0
    blacklisted_tier_seconds: float = 15.0
    max_batch_size: int = 50
    max_concurrent: int = 10


class ScoringConfig(BaseSettings):
    yellow_threshold: float = 30.0
    red_threshold: float = 80.0
    debounce: ScoringDebounceConfig = Field(default_factory=ScoringDebounceConfig)


class IngestConfig(BaseSettings):
    batch_size: int = 500
    flush_interval: float = 2.0
    reconnect_max: float = 60.0
    stale_connection: float = 120.0


class EnrichmentFrequencyConfig(BaseSettings):
    green_hours: float = 6.0
    yellow_hours: float = 2.0
    red_hours: float = 1.0
    blacklisted_hours: float = 0.5


class EnrichmentConfig(BaseSettings):
    opensanctions_rate_limit: int = 10
    fuzzy_name_threshold: float = 80.0
    fuzzy_owner_threshold: float = 75.0
    frequency: EnrichmentFrequencyConfig = Field(default_factory=EnrichmentFrequencyConfig)


class GfwConfig(BaseSettings):
    enabled: bool = False
    base_url: str = "https://gateway.api.globalfishingwatch.org/v3"
    rate_limit_per_second: int = 10
    events_lookback_days: int = 30
    sar_lookback_days: int = 14
    vessel_cache_ttl_hours: int = 24
    # API quota limits (90% of GFW limits: 50K daily, 1.55M monthly)
    daily_request_limit: int = 45000
    monthly_request_limit: int = 1395000
    quota_file_path: str = "/data/raw/.gfw_api_usage.json"


class RetentionConfig(BaseSettings):
    positions_days: int = 365
    compression_days: int = 2


class RawStorageConfig(BaseSettings):
    base_path: str = "/data/raw"
    rotation_interval: int = 3600  # new file every hour
    compress: bool = True


class BatchPipelineConfig(BaseSettings):
    schedule_interval: int = 7200  # run every 2 hours
    load_batch_size: int = 10000
    score_batch_size: int = 100


class ColdStorageConfig(BaseSettings):
    age_days: int = 1
    format: str = "parquet"
    compression: str = "snappy"
    retain_jsonl_days: int = 0  # delete JSONL immediately after Parquet creation


class FrontendConfig(BaseSettings):
    initial_camera_lat: float = 20.0
    initial_camera_lon: float = 30.0
    initial_camera_zoom: float = 2.5
    track_trail_hours: int = 24
    cluster_pixel_range: int = 45


# ---------------------------------------------------------------------------
# Root settings
# ---------------------------------------------------------------------------

class Settings(BaseSettings):
    """Root application settings.

    Loads values from environment variables (prefix-less) and optionally
    merges deeper sections from ``config.yaml`` found next to the project
    root.
    """

    # --- Core env vars ---
    database_url: SecretStr = Field(
        default=SecretStr("postgresql+asyncpg://heimdal:heimdal@localhost:5432/heimdal"),
        description="Async SQLAlchemy database URL",
    )
    redis_url: str = ""
    aisstream_api_key: str = ""
    gfw_api_token: str = ""

    # --- Nested sections ---
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    ingest: IngestConfig = Field(default_factory=IngestConfig)
    enrichment: EnrichmentConfig = Field(default_factory=EnrichmentConfig)
    gfw: GfwConfig = Field(default_factory=GfwConfig)
    retention: RetentionConfig = Field(default_factory=RetentionConfig)
    frontend: FrontendConfig = Field(default_factory=FrontendConfig)
    raw_storage: RawStorageConfig = Field(default_factory=RawStorageConfig)
    batch_pipeline: BatchPipelineConfig = Field(default_factory=BatchPipelineConfig)
    cold_storage: ColdStorageConfig = Field(default_factory=ColdStorageConfig)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    def __repr__(self) -> str:
        """Omit DATABASE_URL (contains credentials) from repr."""
        fields = {
            k: v for k, v in self.__dict__.items() if k != "database_url"
        }
        return f"Settings({fields})"

    def __str__(self) -> str:
        return self.__repr__()


def _find_config_yaml() -> Optional[Path]:
    """Walk up from CWD looking for config.yaml, or check common locations."""
    candidates = [
        Path.cwd() / "config.yaml",
        Path(__file__).resolve().parent.parent / "config.yaml",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def _merge_yaml(settings: Settings, yaml_data: dict[str, Any]) -> Settings:
    """Overlay values from parsed YAML onto an existing Settings instance."""
    section_map = {
        "scoring": "scoring",
        "ingest": "ingest",
        "enrichment": "enrichment",
        "gfw": "gfw",
        "retention": "retention",
        "frontend": "frontend",
        "raw_storage": "raw_storage",
        "batch_pipeline": "batch_pipeline",
        "cold_storage": "cold_storage",
    }
    for yaml_key, attr_name in section_map.items():
        section = yaml_data.get(yaml_key)
        if isinstance(section, dict):
            sub_model = getattr(settings, attr_name)
            for k, v in section.items():
                if hasattr(sub_model, k):
                    current = getattr(sub_model, k)
                    if isinstance(v, dict) and isinstance(current, BaseSettings):
                        # Recursively merge nested sub-models
                        for nk, nv in v.items():
                            if hasattr(current, nk):
                                object.__setattr__(current, nk, nv)
                    else:
                        object.__setattr__(sub_model, k, v)

    # Top-level scalar overrides
    for key in ("redis_url", "aisstream_api_key", "gfw_api_token"):
        if key in yaml_data:
            object.__setattr__(settings, key, yaml_data[key])

    return settings


def load_settings() -> Settings:
    """Create a Settings instance, merging config.yaml if found."""
    s = Settings()
    yaml_path = _find_config_yaml()
    if yaml_path is not None:
        with open(yaml_path) as f:
            data = yaml.safe_load(f) or {}
        s = _merge_yaml(s, data)
    return s


# Singleton instance — importable as ``from shared.config import settings``
settings: Settings = load_settings()
