"""Tests for profiling scripts and performance documentation.

Verifies that:
1. Profiling scripts can be imported without error
2. Key profiled functions exist and are callable
3. docs/PERFORMANCE.md exists with expected content
"""
import importlib
import os
import sys

import pytest

# Ensure project root and service paths are importable
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'services', 'scoring'))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'services', 'ais-ingest'))


class TestProfileScoringImports:
    """Verify that the scoring profiling script can be loaded."""

    def test_profile_scoring_imports(self):
        """profile_scoring.py can be imported as a module."""
        spec = importlib.util.spec_from_file_location(
            "profile_scoring",
            os.path.join(PROJECT_ROOT, "scripts", "profile_scoring.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "main")
        assert hasattr(mod, "profile_aggregation")
        assert hasattr(mod, "profile_rule_evaluation")

    def test_aggregate_score_importable(self):
        """The aggregate_score function targeted by profiling exists."""
        from services.scoring.aggregator import aggregate_score
        assert callable(aggregate_score)

    def test_discover_rules_importable(self):
        """The discover_rules function targeted by profiling exists."""
        from services.scoring.engine import discover_rules
        assert callable(discover_rules)


class TestProfileIngestImports:
    """Verify that the ingest profiling script can be loaded."""

    def test_profile_ingest_imports(self):
        """profile_ingest.py can be imported as a module."""
        spec = importlib.util.spec_from_file_location(
            "profile_ingest",
            os.path.join(PROJECT_ROOT, "scripts", "profile_ingest.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "main")
        assert hasattr(mod, "generate_ais_messages")
        assert hasattr(mod, "profile_parsing")
        assert hasattr(mod, "profile_json_parsing")

    def test_parse_position_report_importable(self):
        """The parse_position_report function targeted by profiling exists."""
        from parser import parse_position_report
        assert callable(parse_position_report)

    def test_generate_ais_messages_produces_data(self):
        """generate_ais_messages returns a list of dicts with expected structure."""
        spec = importlib.util.spec_from_file_location(
            "profile_ingest",
            os.path.join(PROJECT_ROOT, "scripts", "profile_ingest.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        messages = mod.generate_ais_messages(10)
        assert len(messages) == 10
        assert "MessageType" in messages[0]
        assert messages[0]["MessageType"] == "PositionReport"
        assert "MetaData" in messages[0]
        assert "Message" in messages[0]


class TestPerformanceMd:
    """Verify that docs/PERFORMANCE.md exists and has expected content."""

    def test_performance_md_exists(self):
        """docs/PERFORMANCE.md file exists."""
        path = os.path.join(PROJECT_ROOT, "docs", "PERFORMANCE.md")
        assert os.path.isfile(path), f"Expected {path} to exist"

    def test_performance_md_has_bottlenecks(self):
        """PERFORMANCE.md documents identified bottlenecks."""
        path = os.path.join(PROJECT_ROOT, "docs", "PERFORMANCE.md")
        with open(path) as f:
            content = f.read()

        assert "Identified Bottlenecks" in content
        assert "Scoring Engine" in content
        assert "AIS Ingest" in content
        assert "CesiumJS" in content

    def test_performance_md_has_profiling_scripts(self):
        """PERFORMANCE.md references the profiling scripts."""
        path = os.path.join(PROJECT_ROOT, "docs", "PERFORMANCE.md")
        with open(path) as f:
            content = f.read()

        assert "profile_scoring.py" in content
        assert "profile_ingest.py" in content

    def test_performance_md_has_memory_targets(self):
        """PERFORMANCE.md includes memory targets."""
        path = os.path.join(PROJECT_ROOT, "docs", "PERFORMANCE.md")
        with open(path) as f:
            content = f.read()

        assert "Memory Targets" in content
        assert "scoring-engine" in content
        assert "ais-ingest" in content
