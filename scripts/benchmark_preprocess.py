#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import psutil
from scipy import ndimage, special

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brain_atlas_preprocess.io import (  # noqa: E402
    DAPI_GENE,
    DAPI_WAVELENGTH_NM,
    StackMetadata,
    crop_square_zyx,
    preview_angle_to_export_angle,
    read_lsm_metadata,
    rotate_stack_zyx,
    _safe_filename_part,
    _write_stack_mip_png,
    _write_stack_nrrd,
)
from brain_atlas_preprocess.model import ChannelInfo, StackFileState  # noqa: E402


DEFAULT_MANIFEST = Path(
    "/Users/ddharmap/dataProcessing/testOutput/"
    "20260311_f02_tph2_488_optb_546_gbx2_647_Stitch_preprocessed/"
    "preprocess_manifest.json"
)
DEFAULT_OUTPUT_ROOT = Path(
    "/Users/ddharmap/dataProcessing/testOutput/preprocess_benchmark_runs"
)
DEFAULT_VARIANTS = ("loop_gzip", "loop_raw", "batched_gzip", "batched_raw", "fused_raw")
VARIANT_ENCODING = {
    "loop_gzip": "gzip",
    "loop_raw": "raw",
    "batched_gzip": "gzip",
    "batched_raw": "raw",
    "fused_raw": "raw",
}


@dataclass
class MemorySampler:
    interval_seconds: float = 0.02
    peak_rss_bytes: int = 0
    phase_peak_rss_bytes: dict[str, int] = field(default_factory=dict)
    _phase: str = "startup"
    _running: bool = False
    _thread: threading.Thread | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join()

    def set_phase(self, phase: str) -> None:
        with self._lock:
            self._phase = phase

    def _sample_loop(self) -> None:
        process = psutil.Process()
        while self._running:
            rss = process.memory_info().rss
            with self._lock:
                self.peak_rss_bytes = max(self.peak_rss_bytes, rss)
                self.phase_peak_rss_bytes[self._phase] = max(
                    self.phase_peak_rss_bytes.get(self._phase, 0),
                    rss,
                )
            time.sleep(self.interval_seconds)


@dataclass
class RunContext:
    sampler: MemorySampler
    phase_seconds: dict[str, float] = field(default_factory=dict)

    @contextmanager
    def phase(self, name: str):
        self.sampler.set_phase(name)
        start = time.perf_counter()
        try:
            yield
        finally:
            self.phase_seconds[name] = self.phase_seconds.get(name, 0.0) + (
                time.perf_counter() - start
            )


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.run_one:
        return _run_one(args)
    return _run_parent(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark brain-atlas preprocessing variants."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Processed-output manifest to reuse for source path and settings.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Directory where benchmark run folders and summaries are written.",
    )
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--variants",
        nargs="+",
        choices=DEFAULT_VARIANTS,
        default=list(DEFAULT_VARIANTS),
    )
    parser.add_argument("--keep-outputs", action="store_true")
    parser.add_argument("--sample-interval-seconds", type=float, default=0.02)
    parser.add_argument(
        "--synthetic-smoke",
        action="store_true",
        help="Use a tiny generated stack for script tests instead of reading LSM data.",
    )
    parser.add_argument("--run-one", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--variant", choices=DEFAULT_VARIANTS, help=argparse.SUPPRESS)
    parser.add_argument("--repeat-index", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--run-dir", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--result-json", type=Path, help=argparse.SUPPRESS)
    return parser


def _run_parent(args: argparse.Namespace) -> int:
    if args.repeats < 1:
        raise SystemExit("--repeats must be at least 1")

    settings = _load_settings(args)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_root = args.output_root / timestamp
    run_root.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    baseline_output_dir: Path | None = None
    baseline_manifest: dict[str, Any] | None = None

    ordered_variants = list(dict.fromkeys(["loop_gzip", *args.variants]))
    for variant in ordered_variants:
        for repeat_index in range(args.repeats):
            child_run_dir = run_root / f"{variant}_repeat_{repeat_index + 1}"
            result_json = run_root / f"{variant}_repeat_{repeat_index + 1}.json"
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--run-one",
                "--variant",
                variant,
                "--repeat-index",
                str(repeat_index),
                "--run-dir",
                str(child_run_dir),
                "--result-json",
                str(result_json),
                "--sample-interval-seconds",
                str(args.sample_interval_seconds),
            ]
            if args.synthetic_smoke:
                command.append("--synthetic-smoke")
            else:
                command.extend(["--manifest", str(args.manifest)])

            completed = subprocess.run(
                command,
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            if completed.returncode != 0:
                sys.stderr.write(completed.stdout)
                sys.stderr.write(completed.stderr)
                raise SystemExit(completed.returncode)

            result = json.loads(result_json.read_text(encoding="utf-8"))
            output_dir = Path(result["output_dir"])
            manifest = json.loads((output_dir / "preprocess_manifest.json").read_text())

            if variant == "loop_gzip" and repeat_index == 0:
                baseline_output_dir = output_dir
                baseline_manifest = manifest
                result["valid"] = True
                result["correctness"] = {"baseline": True}
            else:
                if baseline_output_dir is None or baseline_manifest is None:
                    raise RuntimeError("Baseline was not produced before candidates.")
                comparison = _compare_output_dirs(
                    baseline_output_dir,
                    baseline_manifest,
                    output_dir,
                    manifest,
                )
                result["valid"] = comparison["valid"]
                result["correctness"] = comparison

            results.append(result)
            if not args.keep_outputs and output_dir != baseline_output_dir:
                shutil.rmtree(child_run_dir, ignore_errors=True)

    if not args.keep_outputs and baseline_output_dir is not None:
        shutil.rmtree(baseline_output_dir.parent, ignore_errors=True)

    summary = {
        "settings": settings,
        "run_root": str(run_root),
        "results": results,
        "aggregate": _aggregate_results(results),
    }
    (run_root / "benchmark_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    _write_summary_csv(run_root / "benchmark_summary.csv", results)
    _print_summary(summary)
    return 0


def _run_one(args: argparse.Namespace) -> int:
    if args.variant is None or args.run_dir is None or args.result_json is None:
        raise SystemExit("--run-one requires --variant, --run-dir, and --result-json")

    args.run_dir.mkdir(parents=True, exist_ok=True)
    sampler = MemorySampler(interval_seconds=args.sample_interval_seconds)
    context = RunContext(sampler=sampler)
    sampler.start()
    started = time.perf_counter()
    try:
        metadata, data, file_state, crop_size_px = _load_case_data(args, context)
        output_dir = _export_variant(
            args.variant,
            metadata,
            data,
            file_state,
            args.run_dir,
            crop_size_px,
            context,
        )
    finally:
        sampler.stop()

    elapsed = time.perf_counter() - started
    result = {
        "variant": args.variant,
        "repeat_index": args.repeat_index,
        "wall_seconds": elapsed,
        "phase_seconds": context.phase_seconds,
        "peak_rss_bytes": sampler.peak_rss_bytes,
        "phase_peak_rss_bytes": sampler.phase_peak_rss_bytes,
        "output_dir": str(output_dir),
        "output_size_bytes": _directory_size(output_dir),
    }
    args.result_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0


def _load_settings(args: argparse.Namespace) -> dict[str, Any]:
    if args.synthetic_smoke:
        return {
            "source_path": "synthetic_smoke.lsm",
            "rotation_degrees": 14.328666854465453,
            "crop_center_yx": [8, 8],
            "crop_size_px": 12,
            "interpolation": "linear",
            "canvas_mode": "expand",
        }
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    return {
        "source_path": manifest["source_path"],
        "rotation_degrees": manifest["rotation_degrees"],
        "crop_center_yx": manifest["crop_center_yx"],
        "crop_size_px": manifest["crop_size_px"],
        "interpolation": manifest["interpolation"],
        "canvas_mode": manifest["canvas_mode"],
    }


def _load_case_data(
    args: argparse.Namespace,
    context: RunContext,
) -> tuple[StackMetadata, np.ndarray, StackFileState, int]:
    settings = _load_settings(args)
    if args.synthetic_smoke:
        channels = [
            ChannelInfo(index=0, gene="gene", wavelength_nm=546),
            ChannelInfo(index=1, gene=DAPI_GENE, wavelength_nm=DAPI_WAVELENGTH_NM),
        ]
        metadata = StackMetadata(
            path=str(args.run_dir / "synthetic_gene_546.lsm"),
            axes="ZCYX",
            shape=(3, 2, 16, 15),
            dtype="uint8",
            channels=channels,
            voxel_size_x_m=1e-6,
            voxel_size_y_m=1e-6,
            voxel_size_z_m=3e-6,
        )
        with context.phase("read"):
            data = np.arange(np.prod(metadata.shape), dtype=np.uint16).reshape(
                metadata.shape
            )
            data = (data % 251).astype(np.uint8)
    else:
        source = Path(settings["source_path"])
        with context.phase("metadata"):
            metadata = read_lsm_metadata(source)
        with context.phase("read"):
            import tifffile

            with tifffile.TiffFile(source) as tiff:
                data = tiff.series[0].asarray()

    crop_center = (
        tuple(settings["crop_center_yx"])
        if settings["crop_center_yx"] is not None
        else None
    )
    file_state = StackFileState(
        path=metadata.path,
        rotation_degrees=float(settings["rotation_degrees"]),
        crop_center_yx=crop_center,
        channels=metadata.channels,
        axes=metadata.axes,
        shape=metadata.shape,
    )
    return metadata, data, file_state, int(settings["crop_size_px"])


def _export_variant(
    variant: str,
    metadata: StackMetadata,
    data: np.ndarray,
    file_state: StackFileState,
    run_dir: Path,
    crop_size_px: int,
    context: RunContext,
) -> Path:
    source = Path(metadata.path)
    output_dir = run_dir / f"{source.stem}_preprocessed"
    output_dir.mkdir(parents=True, exist_ok=True)
    encoding = VARIANT_ENCODING[variant]
    applied_rotation_degrees = preview_angle_to_export_angle(
        file_state.rotation_degrees
    )

    output_files: list[dict[str, Any]] = []
    qc: dict[str, Any] | None = None

    if variant.startswith("batched"):
        with context.phase("transform"):
            rotated = _rotate_zcyx(
                data,
                applied_rotation_degrees,
                interpolation="linear",
                expand_canvas=True,
            )
            transformed = _crop_square_zcyx(
                rotated,
                file_state.crop_center_yx,
                crop_size_px,
            )
        channel_iter = (
            (channel, transformed[:, channel.index, :, :])
            for channel in metadata.channels
        )
    elif variant.startswith("fused"):
        transformed_channels = []
        with context.phase("transform"):
            for channel in metadata.channels:
                transformed_channels.append(
                    (
                        channel,
                        _rotate_crop_stack_zyx_fused(
                            data[:, channel.index, :, :],
                            applied_rotation_degrees,
                            file_state.crop_center_yx,
                            crop_size_px,
                            interpolation="linear",
                            expand_canvas=True,
                        ),
                    )
                )
        channel_iter = iter(transformed_channels)
    else:
        channel_iter = _loop_transformed_channels(
            metadata,
            data,
            applied_rotation_degrees,
            file_state.crop_center_yx,
            crop_size_px,
            context,
        )

    for channel, cropped in channel_iter:
        out_name = (
            f"{source.stem}_{_safe_filename_part(channel.gene)}_"
            f"{channel.wavelength_nm}nm_preprocessed.nrrd"
        )
        out_path = output_dir / out_name
        with context.phase("write_nrrd"):
            _write_stack_nrrd(
                out_path,
                cropped,
                metadata,
                channel=channel,
                rotation_degrees=file_state.rotation_degrees,
                applied_rotation_degrees=applied_rotation_degrees,
                crop_center_yx=file_state.crop_center_yx,
                crop_size_px=crop_size_px,
                encoding=encoding,
                compression_level=9,
            )
        output_files.append(
            {
                "channel": channel.to_dict(),
                "path": str(out_path),
                "shape": list(cropped.shape),
            }
        )
        if channel.gene == DAPI_GENE and channel.wavelength_nm == DAPI_WAVELENGTH_NM:
            with context.phase("qc_manifest"):
                qc_path = output_dir / "preprocess_qc_dapi_mip.png"
                _write_stack_mip_png(qc_path, cropped)
                qc = {
                    "dapi_mip_path": str(qc_path),
                    "rotation_degrees": file_state.rotation_degrees,
                    "applied_rotation_degrees": applied_rotation_degrees,
                }

    with context.phase("qc_manifest"):
        manifest = {
            **metadata.to_manifest_dict(),
            "rotation_degrees": file_state.rotation_degrees,
            "applied_rotation_degrees": applied_rotation_degrees,
            "interpolation": "linear",
            "canvas_mode": "expand",
            "crop_size_px": crop_size_px,
            "crop_center_yx": (
                list(file_state.crop_center_yx)
                if file_state.crop_center_yx is not None
                else None
            ),
            "qc": qc,
            "output_files": output_files,
        }
        (output_dir / "preprocess_manifest.json").write_text(
            json.dumps(manifest, indent=2),
            encoding="utf-8",
        )
    return output_dir


def _loop_transformed_channels(
    metadata: StackMetadata,
    data: np.ndarray,
    applied_rotation_degrees: float,
    crop_center_yx: tuple[int, int] | None,
    crop_size_px: int,
    context: RunContext,
):
    for channel in metadata.channels:
        with context.phase("transform"):
            rotated = rotate_stack_zyx(
                data[:, channel.index, :, :],
                applied_rotation_degrees,
                interpolation="linear",
                expand_canvas=True,
            )
            cropped = crop_square_zyx(rotated, crop_center_yx, crop_size_px)
        yield channel, cropped


def _rotate_zcyx(
    data: np.ndarray,
    angle_degrees: float,
    *,
    interpolation: str,
    expand_canvas: bool,
) -> np.ndarray:
    order = {"nearest": 0, "linear": 1, "cubic": 3}[interpolation]
    rotated = ndimage.rotate(
        data,
        angle=angle_degrees,
        axes=(-2, -1),
        reshape=expand_canvas,
        order=order,
        mode="constant",
        cval=0,
        prefilter=order > 1,
    )
    return rotated.astype(data.dtype, copy=False)


def _crop_square_zcyx(
    data: np.ndarray,
    center_yx: tuple[int, int] | None,
    size_px: int,
) -> np.ndarray:
    if center_yx is None:
        center_y = data.shape[2] // 2
        center_x = data.shape[3] // 2
    else:
        center_y, center_x = center_yx

    start_y = int(center_y) - size_px // 2
    start_x = int(center_x) - size_px // 2
    end_y = start_y + size_px
    end_x = start_x + size_px

    source_start_y = max(0, start_y)
    source_start_x = max(0, start_x)
    source_end_y = min(data.shape[2], end_y)
    source_end_x = min(data.shape[3], end_x)

    cropped = np.zeros((data.shape[0], data.shape[1], size_px, size_px), dtype=data.dtype)
    if source_start_y >= source_end_y or source_start_x >= source_end_x:
        return cropped

    target_start_y = source_start_y - start_y
    target_start_x = source_start_x - start_x
    target_end_y = target_start_y + (source_end_y - source_start_y)
    target_end_x = target_start_x + (source_end_x - source_start_x)
    cropped[:, :, target_start_y:target_end_y, target_start_x:target_end_x] = data[
        :, :, source_start_y:source_end_y, source_start_x:source_end_x
    ]
    return cropped


def _rotate_crop_stack_zyx_fused(
    stack: np.ndarray,
    angle_degrees: float,
    center_yx: tuple[int, int] | None,
    crop_size_px: int,
    *,
    interpolation: str,
    expand_canvas: bool,
) -> np.ndarray:
    order = {"nearest": 0, "linear": 1, "cubic": 3}[interpolation]
    c, s = special.cosdg(angle_degrees), special.sindg(angle_degrees)
    rot_matrix = np.array([[c, s], [-s, c]])
    in_plane_shape = np.asarray(stack.shape[-2:])
    if expand_canvas:
        iy, ix = in_plane_shape
        out_bounds = rot_matrix @ [[0, 0, iy, iy], [0, ix, 0, ix]]
        out_plane_shape = (np.ptp(out_bounds, axis=1) + 0.5).astype(int)
    else:
        out_plane_shape = in_plane_shape

    out_center = rot_matrix @ ((out_plane_shape - 1) / 2)
    in_center = (in_plane_shape - 1) / 2
    offset = in_center - out_center

    if center_yx is None:
        center_y = int(out_plane_shape[0]) // 2
        center_x = int(out_plane_shape[1]) // 2
    else:
        center_y, center_x = center_yx
    crop_start = np.array(
        [int(center_y) - crop_size_px // 2, int(center_x) - crop_size_px // 2]
    )
    crop_offset = offset + rot_matrix @ crop_start

    output = np.empty((stack.shape[0], crop_size_px, crop_size_px), dtype=stack.dtype)
    for z_index in range(stack.shape[0]):
        ndimage.affine_transform(
            stack[z_index],
            rot_matrix,
            crop_offset,
            (crop_size_px, crop_size_px),
            output[z_index],
            order=order,
            mode="constant",
            cval=0,
            prefilter=order > 1,
        )
    return output


def _compare_output_dirs(
    baseline_dir: Path,
    baseline_manifest: dict[str, Any],
    candidate_dir: Path,
    candidate_manifest: dict[str, Any],
) -> dict[str, Any]:
    import nrrd

    details: list[dict[str, Any]] = []
    valid = True
    baseline_outputs = baseline_manifest["output_files"]
    candidate_outputs = candidate_manifest["output_files"]
    if len(baseline_outputs) != len(candidate_outputs):
        return {
            "valid": False,
            "reason": "output file count differs",
            "baseline_count": len(baseline_outputs),
            "candidate_count": len(candidate_outputs),
        }

    for baseline_file, candidate_file in zip(baseline_outputs, candidate_outputs):
        baseline_array, _ = nrrd.read(baseline_file["path"], index_order="C")
        candidate_path = candidate_dir / Path(candidate_file["path"]).name
        candidate_array, _ = nrrd.read(str(candidate_path), index_order="C")
        same = np.array_equal(baseline_array, candidate_array)
        diff_count = 0
        max_abs_diff = 0.0
        if not same:
            valid = False
            diff = np.abs(
                baseline_array.astype(np.float64) - candidate_array.astype(np.float64)
            )
            diff_count = int(np.count_nonzero(diff))
            max_abs_diff = float(diff.max()) if diff.size else 0.0
        details.append(
            {
                "channel": baseline_file["channel"],
                "same": same,
                "diff_count": diff_count,
                "max_abs_diff": max_abs_diff,
                "shape": list(candidate_array.shape),
                "dtype": str(candidate_array.dtype),
            }
        )

    metadata_keys = [
        "rotation_degrees",
        "applied_rotation_degrees",
        "interpolation",
        "canvas_mode",
        "crop_size_px",
        "crop_center_yx",
    ]
    metadata_same = all(
        baseline_manifest.get(key) == candidate_manifest.get(key)
        for key in metadata_keys
    )
    channels_same = [
        item["channel"] for item in baseline_manifest["output_files"]
    ] == [item["channel"] for item in candidate_manifest["output_files"]]
    valid = valid and metadata_same and channels_same
    return {
        "valid": valid,
        "metadata_same": metadata_same,
        "channels_same": channels_same,
        "channels": details,
    }


def _aggregate_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    baseline_times = [
        result["wall_seconds"]
        for result in results
        if result["variant"] == "loop_gzip"
    ]
    baseline_median = _median(baseline_times)
    aggregate: dict[str, Any] = {}
    for variant in sorted({result["variant"] for result in results}):
        variant_results = [result for result in results if result["variant"] == variant]
        wall = [result["wall_seconds"] for result in variant_results]
        aggregate[variant] = {
            "valid_runs": sum(1 for result in variant_results if result.get("valid")),
            "total_runs": len(variant_results),
            "median_wall_seconds": _median(wall),
            "best_wall_seconds": min(wall),
            "median_peak_rss_bytes": _median(
                [result["peak_rss_bytes"] for result in variant_results]
            ),
            "median_output_size_bytes": _median(
                [result["output_size_bytes"] for result in variant_results]
            ),
            "speedup_vs_loop_gzip": (
                baseline_median / _median(wall) if baseline_median else None
            ),
        }
    return aggregate


def _write_summary_csv(path: Path, results: list[dict[str, Any]]) -> None:
    fieldnames = [
        "variant",
        "repeat_index",
        "valid",
        "wall_seconds",
        "peak_rss_bytes",
        "output_size_bytes",
        "metadata_seconds",
        "read_seconds",
        "transform_seconds",
        "write_nrrd_seconds",
        "qc_manifest_seconds",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            phases = result.get("phase_seconds", {})
            writer.writerow(
                {
                    "variant": result["variant"],
                    "repeat_index": result["repeat_index"],
                    "valid": result.get("valid"),
                    "wall_seconds": result["wall_seconds"],
                    "peak_rss_bytes": result["peak_rss_bytes"],
                    "output_size_bytes": result["output_size_bytes"],
                    "metadata_seconds": phases.get("metadata", 0.0),
                    "read_seconds": phases.get("read", 0.0),
                    "transform_seconds": phases.get("transform", 0.0),
                    "write_nrrd_seconds": phases.get("write_nrrd", 0.0),
                    "qc_manifest_seconds": phases.get("qc_manifest", 0.0),
                }
            )


def _print_summary(summary: dict[str, Any]) -> None:
    print(f"Summary written under: {summary['run_root']}")
    print("variant, valid_runs, median_s, speedup, median_peak_rss_mb, median_size_mb")
    for variant, row in summary["aggregate"].items():
        print(
            f"{variant}, {row['valid_runs']}/{row['total_runs']}, "
            f"{row['median_wall_seconds']:.3f}, "
            f"{row['speedup_vs_loop_gzip']:.2f}, "
            f"{row['median_peak_rss_bytes'] / 1024 / 1024:.1f}, "
            f"{row['median_output_size_bytes'] / 1024 / 1024:.1f}"
        )


def _directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _median(values: list[float]) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return float((ordered[middle - 1] + ordered[middle]) / 2)


if __name__ == "__main__":
    raise SystemExit(main())
