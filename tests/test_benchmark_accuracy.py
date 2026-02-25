import json
from pathlib import Path

import pytest

from scripts import benchmark_accuracy


@pytest.mark.unit
def test_recall_denominator_counts_failed_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = {
        "entries": [
            {
                "id": "broken_entry",
                "inputs": {"paystubs_dir": "fixtures", "w2_files": []},
                "settings": {"tax_year": 2025, "tolerance": 0.01},
                "ground_truth": {
                    "household_total_gross_cents": 0,
                    "household_total_fed_cents": 0,
                    "expected_anomalies": ["MISMATCH"],
                    "filers": [],
                },
            }
        ]
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def _raise(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("boom")

    monkeypatch.setattr(benchmark_accuracy, "build_household_package", _raise)

    metrics = benchmark_accuracy.run_benchmark(manifest_path)

    assert metrics["mismatch_rate"] == 100.0
    assert metrics["recall_macro"] == 0.0
    assert metrics["recall_weighted"] == 0.0
    assert metrics["results"][0]["status"] == "ERROR"
    assert metrics["results"][0]["expected_anomalies"] == ["MISMATCH"]
