from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

from brain_atlas_preprocess.io import (
    StackMetadata,
    crop_square_zyx,
    export_preprocessed_channels,
    preview_angle_to_export_angle,
    rotate_stack_zyx,
)
from brain_atlas_preprocess.model import ChannelInfo, StackFileState


def test_gzip_size_differences_do_not_change_decoded_channel_data(
    tmp_path, monkeypatch
):
    nrrd = pytest.importorskip("nrrd")
    channels = [
        ChannelInfo(index=0, gene="zero", wavelength_nm=546),
        ChannelInfo(index=1, gene="sparse", wavelength_nm=488),
        ChannelInfo(index=2, gene="noisy", wavelength_nm=647),
        ChannelInfo(index=3, gene="DAPI", wavelength_nm=740),
    ]
    metadata = StackMetadata(
        path=str(tmp_path / "sample_zero_546_sparse_488_noisy_647.lsm"),
        axes="ZCYX",
        shape=(4, 4, 64, 64),
        dtype="uint8",
        channels=channels,
        voxel_size_x_m=1e-6,
        voxel_size_y_m=1e-6,
        voxel_size_z_m=3e-6,
    )
    data = np.zeros(metadata.shape, dtype=np.uint8)
    data[:, 1, 8:16, 8:16] = 120
    data[:, 2] = np.arange(4 * 64 * 64, dtype=np.uint16).reshape(4, 64, 64) % 251
    data[:, 3, :, :] = 40

    class FakeSeries:
        def asarray(self):
            return data

    class FakeTiffFile:
        def __init__(self, path):
            self.series = [FakeSeries()]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr(
        "brain_atlas_preprocess.io.read_lsm_metadata", lambda path: metadata
    )
    monkeypatch.setattr("brain_atlas_preprocess.io.tifffile.TiffFile", FakeTiffFile)

    output_dir = export_preprocessed_channels(
        StackFileState(
            path=metadata.path,
            rotation_degrees=0.0,
            crop_center_yx=(32, 32),
        ),
        tmp_path,
        interpolation="nearest",
        crop_size_px=64,
        nrrd_encoding="gzip",
    )

    file_sizes = []
    decoded_raw_sizes = []
    for channel in channels:
        out_path = (
            output_dir
            / f"sample_zero_546_sparse_488_noisy_647_{channel.gene}_"
            f"{channel.wavelength_nm}nm_preprocessed.nrrd"
        )
        exported, header = nrrd.read(str(out_path), index_order="C")
        expected = data[:, channel.index, :, :]

        np.testing.assert_array_equal(exported, expected)
        assert exported.shape == (4, 64, 64)
        assert exported.dtype == np.uint8
        assert list(header["sizes"]) == [64, 64, 4]
        assert header["type"] == "uint8"
        assert header["encoding"] == "gzip"

        file_sizes.append(out_path.stat().st_size)
        decoded_raw_sizes.append(exported.nbytes)

    assert len(set(decoded_raw_sizes)) == 1
    assert len(set(file_sizes)) > 1


def test_linear_rotation_can_change_values_without_changing_dtype_or_range():
    stack = np.zeros((1, 24, 24), dtype=np.uint8)
    stack[:, 6:18, 11:13] = 255

    rotated = rotate_stack_zyx(
        stack,
        17.0,
        interpolation="linear",
        expand_canvas=True,
    )

    assert rotated.dtype == np.uint8
    assert rotated.min() >= stack.min()
    assert rotated.max() <= stack.max()
    assert np.setdiff1d(np.unique(rotated), np.array([0, 255], dtype=np.uint8)).size


def test_real_sample_output_matches_recomputed_source_transform():
    nrrd = pytest.importorskip("nrrd")
    tifffile = pytest.importorskip("tifffile")
    output_root = os.environ.get("BRAIN_ATLAS_SAMPLE_OUTPUT_DIR")
    if not output_root:
        pytest.skip("Set BRAIN_ATLAS_SAMPLE_OUTPUT_DIR to audit a local sample output.")

    output_dir = Path(output_root)
    manifest = json.loads((output_dir / "preprocess_manifest.json").read_text())
    source = Path(manifest["source_path"])
    if not source.exists():
        pytest.skip(f"Local source stack is not available: {source}")

    applied_rotation = preview_angle_to_export_angle(manifest["rotation_degrees"])
    crop_center = (
        tuple(manifest["crop_center_yx"])
        if manifest["crop_center_yx"] is not None
        else None
    )
    expand_canvas = manifest["canvas_mode"] == "expand"

    with tifffile.TiffFile(source) as tiff:
        data = tiff.series[0].asarray()

    raw_sizes = set()
    for output_file in manifest["output_files"]:
        channel = output_file["channel"]
        exported, header = nrrd.read(output_file["path"], index_order="C")
        expected = crop_square_zyx(
            rotate_stack_zyx(
                data[:, channel["index"], :, :],
                applied_rotation,
                interpolation=manifest["interpolation"],
                expand_canvas=expand_canvas,
            ),
            crop_center,
            manifest["crop_size_px"],
        )

        np.testing.assert_array_equal(exported, expected)
        assert list(exported.shape) == output_file["shape"]
        assert header["encoding"] in {"gzip", "raw"}
        raw_sizes.add(exported.nbytes)

    assert len(raw_sizes) == 1
