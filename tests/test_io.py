from pathlib import Path

import numpy as np
import pytest

from brain_atlas_preprocess.io import (
    build_channel_mapping,
    load_dapi_mip,
    parse_gene_wavelength_pairs,
    read_lsm_metadata,
    rotate_stack_zyx,
)


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
