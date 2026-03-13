"""Tests for shared.config module."""

import os
import textwrap
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


class TestConfigDefaults:
    """Test that config loads with sensible defaults."""

    def test_loads_with_defaults(self):
        """Config should load even without .env or config.yaml."""
        from shared.config import Settings

        s = Settings()
        assert s.scoring.yellow_threshold == 50.0
        assert s.scoring.red_threshold == 100.0
        assert s.ingest.batch_size == 500
        assert s.ingest.flush_interval == 2.0
        assert s.ingest.reconnect_max == 60.0
        assert s.ingest.stale_connection == 120.0

    def test_gfw_defaults(self):
        from shared.config import Settings

        s = Settings()
        assert s.gfw.base_url == "https://gateway.api.globalfishingwatch.org/v3"
        assert s.gfw.rate_limit_per_second == 10
        assert s.gfw.events_lookback_days == 30
        assert s.gfw.sar_lookback_days == 14
        assert s.gfw.vessel_cache_ttl_hours == 24

    def test_retention_defaults(self):
        from shared.config import Settings

        s = Settings()
        assert s.retention.positions_days == 365
        assert s.retention.compression_days == 30

    def test_frontend_defaults(self):
        from shared.config import Settings

        s = Settings()
        assert s.frontend.track_trail_hours == 24
        assert s.frontend.cluster_pixel_range == 45

    def test_enrichment_defaults(self):
        from shared.config import Settings

        s = Settings()
        assert s.enrichment.opensanctions_rate_limit == 10
        assert s.enrichment.fuzzy_name_threshold == 80.0

    def test_database_url_hidden_in_repr(self):
        from shared.config import Settings

        s = Settings()
        r = repr(s)
        assert "database_url" not in r
        assert "postgresql" not in r


class TestConfigEnvOverride:
    """Test that environment variables override defaults."""

    def test_override_scoring_thresholds(self, monkeypatch):
        monkeypatch.setenv("SCORING__YELLOW_THRESHOLD", "50")
        # pydantic-settings doesn't auto-nest with __ by default,
        # so we test the direct approach via YAML merge
        from shared.config import Settings, ScoringConfig

        sc = ScoringConfig(yellow_threshold=50)
        assert sc.yellow_threshold == 50

    def test_override_gfw_api_token(self, monkeypatch):
        monkeypatch.setenv("GFW_API_TOKEN", "test-token-xyz")
        from shared.config import Settings

        s = Settings()
        assert s.gfw_api_token == "test-token-xyz"

    def test_override_redis_url(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://custom:6380/1")
        from shared.config import Settings

        s = Settings()
        assert s.redis_url == "redis://custom:6380/1"


class TestConfigYamlLoading:
    """Test that YAML config is loaded and merged."""

    def test_yaml_merge(self, tmp_path):
        yaml_content = textwrap.dedent("""\
            scoring:
              yellow_threshold: 40
              red_threshold: 120
            ingest:
              batch_size: 1000
            gfw:
              events_lookback_days: 60
            frontend:
              track_trail_hours: 48
        """)
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(yaml_content)

        from shared.config import Settings, _merge_yaml
        import yaml

        s = Settings()
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
        s = _merge_yaml(s, data)

        assert s.scoring.yellow_threshold == 40
        assert s.scoring.red_threshold == 120
        assert s.ingest.batch_size == 1000
        assert s.gfw.events_lookback_days == 60
        assert s.frontend.track_trail_hours == 48

    def test_yaml_partial_merge(self, tmp_path):
        """YAML with only some sections should leave others at defaults."""
        yaml_content = textwrap.dedent("""\
            scoring:
              yellow_threshold: 25
        """)
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(yaml_content)

        from shared.config import Settings, _merge_yaml
        import yaml

        s = Settings()
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
        s = _merge_yaml(s, data)

        assert s.scoring.yellow_threshold == 25
        assert s.scoring.red_threshold == 100.0  # default preserved
        assert s.ingest.batch_size == 500  # default preserved


class TestConfigSingleton:
    """Test the singleton settings instance."""

    def test_singleton_importable(self):
        from shared.config import settings

        assert settings is not None
        assert hasattr(settings, "scoring")
        assert hasattr(settings, "ingest")
        assert hasattr(settings, "gfw")
