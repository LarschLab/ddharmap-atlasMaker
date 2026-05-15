#!/usr/bin/env python
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import nrrd
import tifffile

from brain_atlas_preprocess.io import (
    crop_square_zyx,
    preview_angle_to_export_angle,
    rotate_stack_zyx,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize NRRD export size, decoded data, and source parity."
    )
    parser.add_argument("output_dir", type=Path)
    parser.add_argument(
        "--verify-source",
        action="store_true",
        help="Recompute each output from the source stack recorded in the manifest.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Write machine-readable JSON instead of a text report.",
    )
    args = parser.parse_args()

    report = diagnose_output_dir(args.output_dir, verify_source=args.verify_source)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_text_report(report)
    return 0


def diagnose_output_dir(output_dir: Path, *, verify_source: bool) -> dict[str, Any]:
    manifest_path = output_dir / "preprocess_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    source_data = _load_source_data(manifest) if verify_source else None
    results = []

    for item in manifest["output_files"]:
        path = Path(item["path"])
        data, header = nrrd.read(str(path), index_order="C")
        stats = _array_stats(data)
        stats.update(
            {
                "channel": item["channel"],
                "path": str(path),
                "file_bytes": path.stat().st_size,
                "decoded_raw_bytes": data.nbytes,
                "compression_ratio": path.stat().st_size / data.nbytes,
                "header_sizes": [int(value) for value in header.get("sizes", [])],
                "header_type": header.get("type"),
                "header_encoding": header.get("encoding"),
            }
        )
        if source_data is not None:
            expected = _expected_from_source(manifest, source_data, item["channel"])
            diff = data.astype(np.int32) - expected.astype(np.int32)
            stats["source_verification"] = {
                "exact_match": bool(np.array_equal(data, expected)),
                "max_abs_diff": int(np.abs(diff).max()) if diff.size else 0,
                "differing_voxels": int(np.count_nonzero(diff)),
            }
        results.append(stats)

    return {
        "output_dir": str(output_dir),
        "manifest_path": str(manifest_path),
        "source_path": manifest.get("source_path"),
        "rotation_degrees": manifest.get("rotation_degrees"),
        "applied_rotation_degrees": manifest.get("applied_rotation_degrees"),
        "interpolation": manifest.get("interpolation"),
        "canvas_mode": manifest.get("canvas_mode"),
        "crop_size_px": manifest.get("crop_size_px"),
        "channels": results,
    }


def _array_stats(data: np.ndarray) -> dict[str, Any]:
    values = data.astype(np.float64, copy=False)
    nonzero = int(np.count_nonzero(data))
    return {
        "shape": [int(dim) for dim in data.shape],
        "dtype": str(data.dtype),
        "min": float(values.min()) if values.size else None,
        "max": float(values.max()) if values.size else None,
        "mean": float(values.mean()) if values.size else None,
        "nonzero": nonzero,
        "zeros": int(data.size - nonzero),
        "unique_count": int(np.unique(data).size),
        "sha256": hashlib.sha256(np.ascontiguousarray(data).tobytes()).hexdigest(),
    }


def _load_source_data(manifest: dict[str, Any]) -> np.ndarray:
    source = Path(manifest["source_path"])
    with tifffile.TiffFile(source) as tiff:
        return tiff.series[0].asarray()


def _expected_from_source(
    manifest: dict[str, Any],
    source_data: np.ndarray,
    channel: dict[str, Any],
) -> np.ndarray:
    crop_center = (
        tuple(manifest["crop_center_yx"])
        if manifest["crop_center_yx"] is not None
        else None
    )
    return crop_square_zyx(
        rotate_stack_zyx(
            source_data[:, channel["index"], :, :],
            preview_angle_to_export_angle(manifest["rotation_degrees"]),
            interpolation=manifest["interpolation"],
            expand_canvas=manifest["canvas_mode"] == "expand",
        ),
        crop_center,
        manifest["crop_size_px"],
    )


def _print_text_report(report: dict[str, Any]) -> None:
    print(f"Output: {report['output_dir']}")
    print(f"Source: {report['source_path']}")
    print(
        "Transform: "
        f"rotation={report['rotation_degrees']} "
        f"applied={report['applied_rotation_degrees']} "
        f"interpolation={report['interpolation']} "
        f"canvas={report['canvas_mode']} "
        f"crop={report['crop_size_px']}"
    )
    for item in report["channels"]:
        channel = item["channel"]
        print()
        print(f"{channel['gene']} {channel['wavelength_nm']} nm")
        print(f"  path: {item['path']}")
        print(
            f"  file/raw bytes: {item['file_bytes']} / "
            f"{item['decoded_raw_bytes']} "
            f"({item['compression_ratio']:.3f})"
        )
        print(
            f"  shape/dtype: {item['shape']} {item['dtype']} "
            f"header sizes={item['header_sizes']} "
            f"type={item['header_type']} encoding={item['header_encoding']}"
        )
        print(
            f"  min/max/mean: {item['min']} / {item['max']} / "
            f"{item['mean']:.6f}"
        )
        print(
            f"  nonzero/zeros/unique: {item['nonzero']} / "
            f"{item['zeros']} / {item['unique_count']}"
        )
        print(f"  sha256: {item['sha256']}")
        verification = item.get("source_verification")
        if verification is not None:
            print(
                "  source verification: "
                f"exact={verification['exact_match']} "
                f"max_abs_diff={verification['max_abs_diff']} "
                f"differing_voxels={verification['differing_voxels']}"
            )


if __name__ == "__main__":
    raise SystemExit(main())
