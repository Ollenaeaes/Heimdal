"""Tests for memory optimization (Story 6 of spec 21).

Verifies that:
1. Scoring engine memory stays below 200MB with 10,000 simulated vessels
2. Ingest buffer memory stays below 10MB with 500 positions
3. Frontend vessel store estimate stays below 100MB for 10,000 vessels
4. The profile_memory.py script can be imported and run without error
"""
import importlib
import os
import sys

import pytest

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'services', 'scoring'))


def _load_profile_memory():
    """Load the profile_memory module from scripts/."""
    spec = importlib.util.spec_from_file_location(
        "profile_memory",
        os.path.join(PROJECT_ROOT, "scripts", "profile_memory.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestMemoryProfileImports:
    """Verify that the memory profiling script can be loaded."""

    def test_profile_memory_imports(self):
        """profile_memory.py can be imported as a module."""
        mod = _load_profile_memory()
        assert hasattr(mod, "main")
        assert hasattr(mod, "profile_scoring_memory")
        assert hasattr(mod, "profile_ingest_buffer")
        assert hasattr(mod, "profile_vessel_store")

    def test_profile_script_runs(self, capsys):
        """profile_memory.py main() runs without error."""
        mod = _load_profile_memory()
        mod.main()
        captured = capsys.readouterr()
        assert "MEMORY PROFILING" in captured.out
        assert "SUMMARY" in captured.out
        assert "All memory targets met!" in captured.out


class TestScoringMemory:
    """Scoring engine memory must stay below 200MB for 10,000 vessels."""

    def test_scoring_memory_below_200mb(self):
        """Scoring state + aggregation for 10,000 vessels uses <200 MB."""
        mod = _load_profile_memory()
        peak_mb = mod.profile_scoring_memory()
        assert peak_mb < 200, (
            f"Scoring engine peak memory {peak_mb:.1f} MB exceeds 200 MB target"
        )

    def test_scoring_memory_reasonable(self):
        """Scoring memory should be well under target (sanity check)."""
        mod = _load_profile_memory()
        peak_mb = mod.profile_scoring_memory()
        # With 10K vessels and 3 anomalies each, memory should be under 50MB
        assert peak_mb < 50, (
            f"Scoring engine peak memory {peak_mb:.1f} MB is unexpectedly high"
        )


class TestIngestBufferMemory:
    """AIS ingest batch buffer must stay below 10MB."""

    def test_ingest_buffer_below_10mb(self):
        """Ingest buffer with 500 positions uses <10 MB."""
        mod = _load_profile_memory()
        peak_mb = mod.profile_ingest_buffer()
        assert peak_mb < 10, (
            f"Ingest buffer peak memory {peak_mb:.1f} MB exceeds 10 MB target"
        )


class TestVesselStoreMemory:
    """Frontend vessel store estimate must stay below 100MB."""

    def test_vessel_store_estimate_below_100mb(self):
        """Vessel store for 10,000 vessels uses <100 MB."""
        mod = _load_profile_memory()
        peak_mb = mod.profile_vessel_store()
        assert peak_mb < 100, (
            f"Frontend store peak memory {peak_mb:.1f} MB exceeds 100 MB target"
        )


class TestPerformanceMdMemorySection:
    """Verify PERFORMANCE.md has memory profiling results."""

    def test_performance_md_has_memory_results(self):
        """PERFORMANCE.md contains memory profiling results section."""
        path = os.path.join(PROJECT_ROOT, "docs", "PERFORMANCE.md")
        with open(path) as f:
            content = f.read()

        assert "Memory Profiling Results" in content
        assert "profile_memory.py" in content

    def test_performance_md_has_scoring_memory(self):
        """PERFORMANCE.md documents scoring engine memory measurement."""
        path = os.path.join(PROJECT_ROOT, "docs", "PERFORMANCE.md")
        with open(path) as f:
            content = f.read()

        assert "10,000 vessels" in content or "10K vessels" in content
        assert "200 MB" in content or "200MB" in content
