"""Graph Build + Signal Scoring Pipeline (Story 8).

Orchestrates the full pipeline:
  1. Build graph from Paris MoU data
  2. Build graph from OpenSanctions data
  3. Build graph from IACS data
  4. Enrich graph with AIS data
  5. Run geographic inference (D signals)
  6. Run per-vessel signal scoring (A/B/C signals)
  7. Run fleet risk propagation (A10, B4)
  8. Update vessel_profiles with final scores and classifications

Supports:
  - Full run (initial bootstrap on MacBook)
  - Incremental run (only re-process vessels with updated data since last run)
  - Single-vessel debugging (--vessel IMO)

Usage:
    python -m services.graph_builder.pipeline
    python -m services.graph_builder.pipeline --incremental
    python -m services.graph_builder.pipeline --vessel 9876543
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras

# Ensure imports work from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from services.graph_builder.builder import GraphBuilder
from services.graph_builder.fleet_propagation import propagate_fleet_risk
from services.graph_builder.schema import init_graph
from services.graph_builder.score_calculator import compute_score
from services.graph_builder.signal_scorer import Signal, SignalScorer
from shared.config import settings
from shared.db.graph import close_graph, get_graph

logger = logging.getLogger("graph-pipeline")


def _get_sync_dsn() -> str:
    """Convert async DATABASE_URL to sync psycopg2 DSN."""
    url = os.environ.get("DATABASE_URL", settings.database_url.get_secret_value())
    return re.sub(r"postgresql\+asyncpg://", "postgresql://", url)


class GraphPipeline:
    """Orchestrates graph build, scoring, and vessel profile updates."""

    def __init__(self):
        self.graph = get_graph()
        self.pg = psycopg2.connect(_get_sync_dsn())
        self.pg.autocommit = False

    def close(self):
        self.pg.close()
        close_graph()

    def run_full(self) -> dict:
        """Run the full pipeline (initial bootstrap)."""
        logger.info("=== FULL PIPELINE ===")
        t0 = time.time()
        stats = {}

        # Stage 1-3: Build graph from static sources
        logger.info("--- Stage 1-3: Graph Build (static sources) ---")
        builder = GraphBuilder(graph=self.graph, pg_conn=self.pg)
        build_stats = builder.build_all()
        stats["graph_build"] = {
            "nodes": dict(build_stats.nodes),
            "edges": dict(build_stats.edges),
            "transitions": build_stats.transitions,
        }

        # Stage 4: Enrich graph with AIS data
        logger.info("--- Stage 4: AIS Enrichment ---")
        builder.enrich_from_ais()
        stats["ais_enrichment"] = {"sts_partner_edges": build_stats.edges.get("STS_PARTNER", 0)}

        # Stage 5: Geographic inference (D signals)
        logger.info("--- Stage 5: Geographic Inference ---")
        d_count = self._run_geographic_inference()
        stats["geographic_inference"] = {"d_signals": d_count}

        # Stage 6-7: Signal scoring + fleet propagation
        logger.info("--- Stage 6-7: Signal Scoring + Fleet Propagation ---")
        score_stats = self._score_all_vessels()
        stats["scoring"] = score_stats

        # Stage 8: Update vessel_profiles
        logger.info("--- Stage 8: Update vessel_profiles ---")
        update_count = self._update_vessel_profiles()
        stats["profile_updates"] = update_count

        elapsed = time.time() - t0
        stats["elapsed"] = round(elapsed, 1)
        logger.info("=== FULL PIPELINE COMPLETE in %.1fs ===", elapsed)
        self._log_stats(stats)
        return stats

    def run_incremental(self) -> dict:
        """Run incremental pipeline — only vessels with updated source data."""
        logger.info("=== INCREMENTAL PIPELINE ===")
        t0 = time.time()
        stats = {}

        # Find vessels updated since last run
        updated_imos = self._find_recently_updated_vessels()
        if not updated_imos:
            logger.info("No vessels with updated data")
            return {"vessels_processed": 0}

        logger.info("Found %d vessels with updated data", len(updated_imos))

        # Build/update graph for these vessels only
        builder = GraphBuilder(graph=self.graph, pg_conn=self.pg)
        init_graph(self.graph)
        builder.build_from_paris_mou()  # Idempotent — only creates/updates
        builder.build_from_opensanctions()
        builder.build_from_iacs()
        builder.enrich_from_ais()

        # Score only updated vessels
        score_stats = self._score_vessels(updated_imos)
        stats["scoring"] = score_stats
        stats["vessels_processed"] = len(updated_imos)

        update_count = self._update_vessel_profiles(imos=updated_imos)
        stats["profile_updates"] = update_count

        elapsed = time.time() - t0
        stats["elapsed"] = round(elapsed, 1)
        logger.info("=== INCREMENTAL PIPELINE COMPLETE in %.1fs ===", elapsed)
        return stats

    def run_single_vessel(self, imo: int) -> dict:
        """Run pipeline for a single vessel (debugging mode)."""
        logger.info("=== SINGLE VESSEL PIPELINE: IMO %d ===", imo)
        t0 = time.time()

        # Ensure graph is initialized
        init_graph(self.graph)

        # Score this vessel
        scorer = SignalScorer(pg_conn=self.pg, graph=self.graph)
        signals = scorer.evaluate_vessel(imo)

        # Fleet propagation
        fleet_signals = propagate_fleet_risk(self.graph, imo)
        all_signals = signals + [
            Signal(s.signal_id, s.weight, s.details, s.source_data)
            for s in fleet_signals
        ]

        # Check sanctioned status
        is_sanctioned = scorer.is_vessel_sanctioned(imo)
        total_score, classification = compute_score(all_signals, is_sanctioned)

        # Update this vessel's profile
        self._update_single_vessel(imo, total_score, classification, all_signals)

        elapsed = time.time() - t0

        result = {
            "imo": imo,
            "signals": [
                {"id": s.signal_id, "weight": s.weight, "details": s.details}
                for s in all_signals
            ],
            "total_score": total_score,
            "classification": classification,
            "is_sanctioned": is_sanctioned,
            "elapsed": round(elapsed, 3),
        }

        logger.info("Vessel %d: score=%.1f, classification=%s, signals=%d",
                     imo, total_score, classification, len(all_signals))
        return result

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    def _run_geographic_inference(self) -> int:
        """Run geographic inference for all vessels with positions."""
        from services.geographic_inference.engine import GeographicInference

        geo = GeographicInference(pg_conn=self.pg)
        with self.pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT DISTINCT mmsi FROM vessel_profiles
                WHERE last_lat IS NOT NULL AND imo IS NOT NULL
            """)
            mmsis = [row["mmsi"] for row in cur.fetchall()]

        total_signals = 0
        for mmsi in mmsis:
            try:
                signals = geo.evaluate_vessel(mmsi)
                if signals:
                    geo.store_signals(mmsi, signals)
                    total_signals += len(signals)
            except Exception:
                logger.exception("Geographic inference failed for MMSI %d", mmsi)

        self.pg.commit()
        logger.info("Geographic inference: %d signals for %d vessels", total_signals, len(mmsis))
        return total_signals

    def _score_all_vessels(self) -> dict:
        """Score all vessels with IMOs in the graph."""
        result = self.graph.query("MATCH (v:Vessel) RETURN v.imo")
        all_imos = [row[0] for row in result.result_set if row[0] is not None]
        return self._score_vessels(all_imos)

    def _score_vessels(self, imos: list[int]) -> dict:
        """Score a list of vessels and store results."""
        scorer = SignalScorer(pg_conn=self.pg, graph=self.graph)
        stats = {"scored": 0, "errors": 0, "by_tier": {"green": 0, "yellow": 0, "red": 0, "blacklisted": 0}}

        for imo in imos:
            try:
                signals = scorer.evaluate_vessel(imo)

                # Fleet propagation (runs AFTER individual scoring)
                fleet_signals = propagate_fleet_risk(self.graph, imo)
                all_signals = signals + [
                    Signal(s.signal_id, s.weight, s.details, s.source_data)
                    for s in fleet_signals
                ]

                is_sanctioned = scorer.is_vessel_sanctioned(imo)
                total_score, classification = compute_score(all_signals, is_sanctioned)

                # Store signal details in vessel_signals table
                self._store_vessel_signals(imo, all_signals)

                # Update graph node classification
                self.graph.query(
                    "MATCH (v:Vessel {imo: $imo}) SET v.score = $score, v.classification = $cls",
                    {"imo": imo, "score": total_score, "cls": classification},
                )

                stats["scored"] += 1
                stats["by_tier"][classification] += 1

            except Exception:
                logger.exception("Scoring failed for IMO %d", imo)
                stats["errors"] += 1

        logger.info("Scoring: %d scored, %d errors, tiers=%s",
                     stats["scored"], stats["errors"], stats["by_tier"])
        return stats

    def _store_vessel_signals(self, imo: int, signals: list[Signal]) -> None:
        """Store signal details in vessel_signals table."""
        import json
        with self.pg.cursor() as cur:
            for s in signals:
                cur.execute("""
                    INSERT INTO vessel_signals (mmsi, imo, signal_id, weight, triggered_at, details, source_data)
                    SELECT vp.mmsi, %s, %s, %s, NOW(), %s, %s
                    FROM vessel_profiles vp WHERE vp.imo = %s
                    ON CONFLICT ON CONSTRAINT vessel_signals_mmsi_signal_id_triggered_at_idx
                    DO UPDATE SET weight = EXCLUDED.weight, details = EXCLUDED.details
                """, (imo, s.signal_id, s.weight, json.dumps(s.details), s.source_data, imo))
        self.pg.commit()

    def _update_vessel_profiles(self, imos: list[int] | None = None) -> int:
        """Update vessel_profiles.risk_score and risk_tier from graph."""
        if imos:
            imo_filter = "AND v.imo = ANY(%s)"
        else:
            imo_filter = ""

        # Read scores from graph
        result = self.graph.query(
            "MATCH (v:Vessel) WHERE v.score IS NOT NULL RETURN v.imo, v.score, v.classification"
        )

        updated = 0
        with self.pg.cursor() as cur:
            for row in result.result_set:
                graph_imo, score, classification = row[0], row[1], row[2]
                if imos and graph_imo not in imos:
                    continue
                if classification is None:
                    continue

                cur.execute("""
                    UPDATE vessel_profiles
                    SET risk_score = %s, risk_tier = %s, updated_at = NOW()
                    WHERE imo = %s
                """, (score, classification, graph_imo))
                updated += cur.rowcount

        self.pg.commit()
        logger.info("Updated %d vessel profiles", updated)
        return updated

    def _update_single_vessel(self, imo: int, score: float, classification: str,
                               signals: list[Signal]) -> None:
        """Update a single vessel's profile and store signals."""
        import json

        # Update graph node
        self.graph.query(
            "MATCH (v:Vessel {imo: $imo}) SET v.score = $score, v.classification = $cls",
            {"imo": imo, "score": score, "cls": classification},
        )

        # Update vessel_profiles
        with self.pg.cursor() as cur:
            cur.execute("""
                UPDATE vessel_profiles
                SET risk_score = %s, risk_tier = %s, updated_at = NOW()
                WHERE imo = %s
            """, (score, classification, imo))

        # Store signals
        self._store_vessel_signals(imo, signals)
        self.pg.commit()

    def _find_recently_updated_vessels(self) -> list[int]:
        """Find vessels with data updated since last pipeline run."""
        with self.pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Check for new/updated inspections, IACS changes, or OpenSanctions updates
            cur.execute("""
                SELECT DISTINCT imo FROM (
                    SELECT imo FROM psc_inspections
                    WHERE created_at > NOW() - INTERVAL '24 hours'
                    UNION
                    SELECT imo FROM iacs_vessels_current
                    WHERE last_seen > NOW() - INTERVAL '24 hours'
                    UNION
                    SELECT vl.imo::INTEGER FROM os_vessel_links vl
                    JOIN os_entities e ON e.entity_id = vl.entity_id
                    WHERE e.last_seen > NOW() - INTERVAL '24 hours'
                    AND vl.imo IS NOT NULL
                ) updated
                WHERE imo IS NOT NULL
            """)
            return [row["imo"] for row in cur.fetchall()]

    def _log_stats(self, stats: dict) -> None:
        """Log pipeline stats summary."""
        for key, value in stats.items():
            if isinstance(value, dict):
                logger.info("  %s: %s", key, value)
            else:
                logger.info("  %s: %s", key, value)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(description="Graph Build + Signal Scoring Pipeline")
    parser.add_argument("--incremental", action="store_true",
                        help="Only process vessels with updated data")
    parser.add_argument("--vessel", type=int, metavar="IMO",
                        help="Score a single vessel (debugging mode)")
    args = parser.parse_args()

    pipeline = GraphPipeline()
    try:
        if args.vessel:
            result = pipeline.run_single_vessel(args.vessel)
            print(f"\nVessel {args.vessel}:")
            print(f"  Score: {result['total_score']}")
            print(f"  Classification: {result['classification']}")
            print(f"  Sanctioned: {result['is_sanctioned']}")
            print(f"  Signals ({len(result['signals'])}):")
            for s in result["signals"]:
                print(f"    {s['id']} (weight {s['weight']}): {s['details'].get('reason', '')}")
        elif args.incremental:
            pipeline.run_incremental()
        else:
            pipeline.run_full()
    finally:
        pipeline.close()


if __name__ == "__main__":
    main()
