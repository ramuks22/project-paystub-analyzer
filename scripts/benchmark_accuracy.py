#!/usr/bin/env python3
import json
import argparse
import sys
import hashlib
import time
from pathlib import Path
from decimal import Decimal
from typing import Any, Dict

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from paystub_analyzer.annual import build_household_package, collect_annual_snapshots  # noqa: E402


def compute_hash(data: Any) -> str:
    """Compute a stable SHA-256 hash of a JSON-serializable object."""
    encoded = json.dumps(data, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


# ROADMAP ANOMALY CLASSES
ANOMALY_MAP = {
    "ytd_calc_decrease": "YTD_DROP",
    "state_ytd_decrease": "YTD_DROP",
    "ytd_calc_mismatch": "CONSISTENCY_ERROR",
    "state_ytd_calc_mismatch": "CONSISTENCY_ERROR",
    "duplicate_pay_date": "SEQUENCE_GAP",
    "SEQUENCE_GAP": "SEQUENCE_GAP",
    "missing_final_values": "MISMATCH",
    "OUTLIER_EARNINGS": "CONSISTENCY_ERROR",
}

ANOMALY_WEIGHTS = {
    "MISMATCH": 1.0,  # Filing killer
    "YTD_DROP": 0.8,  # Critical continuity break
    "CONSISTENCY_ERROR": 0.6,  # Math error (often OCR)
    "SEQUENCE_GAP": 0.4,  # Missing data
}


def run_benchmark(manifest_path: Path) -> Dict[str, Any]:
    with manifest_path.open("r", encoding="utf-8") as f:
        manifest = json.load(f)

    base_dir = manifest_path.parent
    results = []

    total_mismatches = 0
    total_comparison_rows = 0

    # KPI Accumulators
    class_stats = {cls: {"detected": 0, "labeled": 0} for cls in ANOMALY_WEIGHTS.keys()}

    start_time = time.time()

    for entry in manifest["entries"]:
        entry_id = entry["id"]
        inputs = entry["inputs"]
        settings = entry["settings"]
        gt = entry["ground_truth"]
        entry_mismatches = 0

        tax_year = settings["tax_year"]
        render_scale = settings.get("render_scale", 2.8)
        tolerance = Decimal(str(settings.get("tolerance", 0.01)))

        # Construct implicit household config from manifest entry
        household_config = {"version": "0.4.0", "household_id": entry_id, "filers": []}

        # For simplicity in benchmarking, we assume entry ground_truth filers map to sources
        # This is a bit simplified; real ones use actual maps.
        # We'll assume a single filer if inputs aren't keyed per filer.
        household_config["filers"].append(
            {
                "id": "primary",
                "role": "PRIMARY",
                "sources": {"paystubs_dir": inputs["paystubs_dir"], "w2_files": inputs["w2_files"]},
            }
        )

        def snapshot_loader(source_cfg: dict) -> list:
            d = base_dir / source_cfg["paystubs_dir"]
            return collect_annual_snapshots(paystubs_dir=d, year=tax_year, render_scale=render_scale)

        def w2_loader(source_cfg: dict) -> dict | None:
            files = source_cfg.get("w2_files", [])
            if not files:
                return None
            # Placeholder for W-2 loading if needed
            return None

        # [P1] Pre-calculate expected anomalies to ensure recall denominator is accurate
        # even if processing fails in the try block.
        expected_classes = set()
        for e_cls in gt.get("expected_anomalies", []):
            expected_classes.add(e_cls)
        for filer in gt.get("filers", []):
            for e_cls in filer.get("expected_anomalies", []):
                expected_classes.add(e_cls)

        # Update stats for recall (denominator part)
        for cls in ANOMALY_WEIGHTS.keys():
            if cls in expected_classes:
                class_stats[cls]["labeled"] += 1

        # Execute
        print(f"Benchmarking: {entry_id}...", end="", flush=True)
        try:
            composite = build_household_package(
                household_config=household_config,
                tax_year=tax_year,
                snapshot_loader=snapshot_loader,
                w2_loader=w2_loader,
                tolerance=tolerance,
            )
            report = composite["report"]
            print("Done.")

            # Score Household Totals
            actual_gross = report["household_summary"]["total_gross_pay_cents"]
            actual_fed = report["household_summary"]["total_fed_tax_cents"]

            gt_gross = gt["household_total_gross_cents"]
            gt_fed = gt["household_total_fed_cents"]

            entry_mismatches = 0
            if actual_gross != gt_gross:
                entry_mismatches += 1
            if actual_fed != gt_fed:
                entry_mismatches += 1

            total_mismatches += entry_mismatches
            total_comparison_rows += 2

            # Score Anomalies
            detected_classes = set()
            for flr_analysis in composite.get("filers_analysis", []):
                inner_meta = flr_analysis.get("internal", {}).get("meta", {})
                detected_issues = inner_meta.get("consistency_issues", [])
                if detected_issues:
                    print(f" Detected Codes: {[i['code'] for i in detected_issues]}", end="", flush=True)
                for issue in detected_issues:
                    code = issue.get("code")
                    cls = ANOMALY_MAP.get(code)
                    if cls:
                        detected_classes.add(cls)

            # Update stats for recall (numerator part)
            for cls in detected_classes:
                if cls in expected_classes:
                    class_stats[cls]["detected"] += 1

            # Sort for reproducibility
            results.append(
                {
                    "id": entry_id,
                    "status": "PASS" if entry_mismatches == 0 else "FAIL",
                    "mismatches": entry_mismatches,
                    "expected_anomalies": sorted(list(expected_classes)),
                    "detected_anomalies": sorted(list(detected_classes)),
                    "report_hash": compute_hash(report),
                }
            )
        except Exception as e:
            print(f"FAILED: {e}")
            total_mismatches += 2  # Treat processing failure as total mismatch for metrics
            total_comparison_rows += 2
            results.append(
                {
                    "id": entry_id,
                    "status": "ERROR",
                    "error": str(e),
                    "mismatches": 2,
                    "expected_anomalies": sorted(list(expected_classes)),
                    "detected_anomalies": [],
                }
            )
            continue

    duration = time.time() - start_time

    # KPI Calculation
    mismatch_rate = (total_mismatches / total_comparison_rows) * 100 if total_comparison_rows > 0 else 0

    # Recall Math
    recalls = []
    weighted_top = 0.0
    weighted_bottom = 0.0

    for cls, stats in class_stats.items():
        if stats["labeled"] > 0:
            recall = stats["detected"] / stats["labeled"]
            recalls.append(recall)
            w = ANOMALY_WEIGHTS[cls]
            weighted_top += recall * w * stats["labeled"]
            weighted_bottom += w * stats["labeled"]

    recall_macro = (sum(recalls) / len(recalls)) * 100 if recalls else 100.0
    recall_weighted = (weighted_top / weighted_bottom) * 100 if weighted_bottom > 0 else 100.0

    metrics = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_sec": round(duration, 2),
        "total_entries": len(results),
        "mismatch_rate": round(mismatch_rate, 4),
        "recall_macro": round(recall_macro, 2),
        "recall_weighted": round(recall_weighted, 2),
        "results": results,
    }

    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("tests/fixtures/gold/manifest.json"))
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--verify-reproducibility", action="store_true")

    args = parser.parse_args()

    metrics = run_benchmark(args.manifest)

    if args.verify_reproducibility:
        print("Verifying reproducibility...", end="", flush=True)
        metrics2 = run_benchmark(args.manifest)

        # Normalize variable fields for bit-identical check
        def normalize_for_copy(m: dict) -> dict:
            m_copy = json.loads(json.dumps(m))
            m_copy["timestamp"] = "normalized"
            m_copy["duration_sec"] = 0.0
            return m_copy

        if normalize_for_copy(metrics) == normalize_for_copy(metrics2):
            print("OK (Bit-Identical Report Hashes & Normalized Metrics)")
        else:
            print("CRITICAL: Non-deterministic results detected!")
            sys.exit(1)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)
        print(f"Metrics saved to {args.out}")
    else:
        print(json.dumps(metrics, indent=2))

    if metrics["mismatch_rate"] > 0 or any(r["status"] == "ERROR" for r in metrics["results"]):
        print("\nFATAL: Accuracy benchmark failed or encountered errors.")
        sys.exit(1)
