from pathlib import Path

import numpy as np
import pytest

from brain_atlas_preprocess.io import (
    StackMetadata,
    build_channel_mapping,
    crop_square_zyx,
    export_preprocessed_channels,
    load_dapi_mip,
    parse_gene_wavelength_pairs,
    read_lsm_metadata,
    rotate_stack_zyx,
)
from brain_atlas_preprocess.model import ChannelInfo, StackFileState


def test_parse_gene_wavelength_pairs_full_channel_name():
    pairs = parse_gene_wavelength_pairs(
        "20260311_f01_crha_488_calb2(a)_546_crhb_647_Stitch.lsm"
    )

    assert pairs == {488: "crha", 546: "calb2(a)", 647: "crhb"}


def test_parse_gene_wavelength_pairs_missing_647():
    pairs = parse_gene_wavelength_pairs("20260320_f01_slc17a6b_488_npy_546_Stitch.lsm")

    assert pairs == {488: "slc17a6b", 546: "npy"}


def test_channel_mapping_uses_expected_file_order_for_four_channels():
    channels = build_channel_mapping(
        "20260312_f02_arxa_488_shha_546_mc4r_647_Stitch.lsm",
        channel_count=4,
    )

    assert [(c.index, c.gene, c.wavelength_nm) for c in channels] == [
        (0, "shha", 546),
        (1, "arxa", 488),
        (2, "mc4r", 647),
        (3, "DAPI", 740),
    ]


def test_channel_mapping_filters_missing_wavelengths_for_three_channels():
    channels = build_channel_mapping(
        "20260317_f01_dlk1_488_homer1b_647_Stitch.lsm",
        channel_count=3,
    )

    assert [(c.index, c.gene, c.wavelength_nm) for c in channels] == [
        (0, "dlk1", 488),
        (1, "homer1b", 647),
        (2, "DAPI", 740),
    ]


def test_channel_mapping_rejects_count_mismatch():
    with pytest.raises(ValueError, match="Parsed 4 channels"):
        build_channel_mapping(
            "20260312_f02_arxa_488_shha_546_mc4r_647_Stitch.lsm",
            channel_count=3,
        )


def test_rotate_stack_zero_degrees_preserves_data_and_dtype():
    stack = np.arange(2 * 4 * 5, dtype=np.uint8).reshape(2, 4, 5)

    rotated = rotate_stack_zyx(stack, 0.0)

    assert rotated.dtype == np.uint8
    np.testing.assert_array_equal(rotated, stack)
    assert rotated is not stack


def test_rotate_stack_expands_canvas_and_preserves_dtype():
    stack = np.zeros((2, 5, 5), dtype=np.uint8)
    stack[:, 2, :] = 255

    rotated = rotate_stack_zyx(stack, 45.0, interpolation="linear", expand_canvas=True)

    assert rotated.dtype == np.uint8
    assert rotated.shape[0] == stack.shape[0]
    assert rotated.shape[1] > stack.shape[1]
    assert rotated.shape[2] > stack.shape[2]
    assert rotated[:, 0, 0].max() == 0


def test_crop_square_uses_center_and_preserves_dtype():
    stack = np.arange(2 * 6 * 7, dtype=np.uint16).reshape(2, 6, 7)

    cropped = crop_square_zyx(stack, (3, 4), 3)

    assert cropped.dtype == np.uint16
    assert cropped.shape == (2, 3, 3)
    np.testing.assert_array_equal(cropped, stack[:, 2:5, 3:6])


def test_crop_square_pads_out_of_bounds_with_zero():
    stack = np.ones((1, 4, 4), dtype=np.uint8)

    cropped = crop_square_zyx(stack, (0, 0), 4)

    assert cropped.shape == (1, 4, 4)
    np.testing.assert_array_equal(
        cropped[0],
        np.array(
            [
                [0, 0, 0, 0],
                [0, 0, 0, 0],
                [0, 0, 1, 1],
                [0, 0, 1, 1],
            ],
            dtype=np.uint8,
        ),
    )


def test_export_preprocessed_channels_writes_nrrd_with_metadata(tmp_path, monkeypatch):
    nrrd = pytest.importorskip("nrrd")
    channels = [
        ChannelInfo(index=0, gene="gene_a", wavelength_nm=488),
        ChannelInfo(index=1, gene="DAPI", wavelength_nm=740),
    ]
    metadata = StackMetadata(
        path=str(tmp_path / "sample_gene_a_488.lsm"),
        axes="ZCYX",
        shape=(2, 2, 4, 4),
        dtype="uint16",
        channels=channels,
        voxel_size_x_m=1e-6,
        voxel_size_y_m=2e-6,
        voxel_size_z_m=3e-6,
    )
    data = np.arange(2 * 2 * 4 * 4, dtype=np.uint16).reshape(2, 2, 4, 4)

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

    monkeypatch.setattr("brain_atlas_preprocess.io.read_lsm_metadata", lambda path: metadata)
    monkeypatch.setattr("brain_atlas_preprocess.io.tifffile.TiffFile", FakeTiffFile)

    output_dir = export_preprocessed_channels(
        StackFileState(
            path=metadata.path,
            rotation_degrees=0.0,
            crop_center_yx=(1, 1),
        ),
        tmp_path,
        crop_size_px=2,
    )

    out_path = output_dir / "sample_gene_a_488_gene_a_488nm_preprocessed.nrrd"
    exported, header = nrrd.read(str(out_path))
    assert exported.shape == (2, 2, 2)
    assert exported.dtype == np.uint16
    assert header["source_axes"] == "ZCYX"
    assert header["channel_gene"] == "gene_a"
    assert header["rotation_degrees"] == "0.0"
    assert header["crop_size_px"] == "2"
    assert list(header["spacings"]) == [3.0, 2.0, 1.0]


def test_optional_sample_smoke():
    sample = Path("/Users/ddharmap/dataProcessing/testSample/20260312_f02_arxa_488_shha_546_mc4r_647_Stitch.lsm")
    if not sample.exists():
        pytest.skip("Local sample data is not available.")

    metadata = read_lsm_metadata(sample)
    mip = load_dapi_mip(sample)

    assert metadata.axes == "ZCYX"
    assert metadata.shape[1] == 4
    assert len(metadata.channels) == 4
    assert mip.shape == metadata.shape[-2:]
