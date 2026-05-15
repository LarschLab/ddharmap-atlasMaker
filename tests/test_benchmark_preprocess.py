from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


def test_benchmark_preprocess_synthetic_smoke(tmp_path):
    pytest.importorskip("psutil")
    script = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_preprocess.py"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--synthetic-smoke",
            "--output-root",
            str(tmp_path),
            "--variants",
            "loop_raw",
            "loop_gzip",
            "loop_raw_threads_2",
            "--repeats",
            "1",
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    run_dirs = [path for path in tmp_path.iterdir() if path.is_dir()]
    assert len(run_dirs) == 1
    summary = json.loads((run_dirs[0] / "benchmark_summary.json").read_text())
    results = {result["variant"]: result for result in summary["results"]}

    assert {"loop_gzip", "loop_raw", "loop_raw_threads_2"} <= set(results)
    assert results["loop_raw"]["valid"] is True
    assert results["loop_gzip"]["valid"] is True
    assert results["loop_raw_threads_2"]["valid"] is True
    assert results["loop_gzip"]["correctness"]["valid"] is True
    assert results["loop_raw_threads_2"]["correctness"]["valid"] is True
    assert results["loop_raw"]["phase_seconds"]["transform"] > 0
    assert results["loop_raw"]["phase_seconds"]["write_nrrd"] > 0
    assert results["loop_raw"]["peak_rss_bytes"] > 0
    assert (run_dirs[0] / "benchmark_summary.csv").exists()


def test_benchmark_preprocess_mps_synthetic_smoke(tmp_path):
    pytest.importorskip("psutil")
    torch = pytest.importorskip("torch")
    if not torch.backends.mps.is_available():
        pytest.skip("PyTorch MPS is not available.")

    script = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_preprocess.py"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--synthetic-smoke",
            "--output-root",
            str(tmp_path),
            "--variants",
            "loop_raw",
            "--include-mps",
            "--repeats",
            "1",
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    run_dirs = [path for path in tmp_path.iterdir() if path.is_dir()]
    assert len(run_dirs) == 1
    summary = json.loads((run_dirs[0] / "benchmark_summary.json").read_text())
    results = {result["variant"]: result for result in summary["results"]}

    assert results["loop_raw"]["valid"] is True
    assert "mps_fused_raw" in results
    assert "correctness" in results["mps_fused_raw"]
    assert results["mps_fused_raw"]["mps_memory_bytes"]["recommended_max_memory"] > 0
    assert results["mps_fused_raw"]["correctness"]["channels"]
