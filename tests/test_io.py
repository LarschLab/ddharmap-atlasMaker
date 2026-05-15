from pathlib import Path
import json
import struct
import zlib

import numpy as np
import pytest

from brain_atlas_preprocess.io import (
    StackMetadata,
    build_channel_mapping,
    crop_square_zyx,
    export_preprocessed_channels,
    load_dapi_mip,
    parse_gene_wavelength_pairs,
    preview_angle_to_export_angle,
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


def test_preview_angle_to_export_angle_matches_qt_visual_direction():
    assert preview_angle_to_export_angle(90.0) == -90.0
    assert preview_angle_to_export_angle(-12.5) == 12.5
    assert preview_angle_to_export_angle(0.0) == -0.0


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
        shape=(3, 2, 4, 4),
        dtype="uint16",
        channels=channels,
        voxel_size_x_m=1e-6,
        voxel_size_y_m=2e-6,
        voxel_size_z_m=3e-6,
    )
    data = np.arange(3 * 2 * 4 * 4, dtype=np.uint16).reshape(3, 2, 4, 4)

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
            crop_center_yx=(1, 1),
        ),
        tmp_path,
        crop_size_px=2,
    )

    out_path = output_dir / "sample_gene_a_488_gene_a_488nm_preprocessed.nrrd"
    exported, header = nrrd.read(str(out_path), index_order="C")
    expected = data[:, 0, 0:2, 0:2]
    assert exported.shape == (3, 2, 2)
    assert exported.dtype == np.uint16
    np.testing.assert_array_equal(exported, expected)
    assert list(header["sizes"]) == [2, 2, 3]
    assert header["source_axes"] == "ZCYX"
    assert header["array_axes"] == "ZYX"
    assert header["channel_gene"] == "gene_a"
    assert header["rotation_degrees"] == "0.0"
    assert header["applied_rotation_degrees"] == "-0.0"
    assert header["crop_size_px"] == "2"
    assert header["space dimension"] == 3
    np.testing.assert_array_equal(
        header["space directions"],
        np.array(
            [
                [1.0, 0.0, 0.0],
                [0.0, 2.0, 0.0],
                [0.0, 0.0, 3.0],
            ]
        ),
    )
    assert header["space units"] == ["um", "um", "um"]
    manifest = json.loads((output_dir / "preprocess_manifest.json").read_text())
    assert manifest["rotation_degrees"] == 0.0
    assert manifest["applied_rotation_degrees"] == -0.0
    assert manifest["qc"]["rotation_degrees"] == 0.0
    assert manifest["qc"]["applied_rotation_degrees"] == -0.0
    assert Path(manifest["qc"]["dapi_mip_path"]).name == "preprocess_qc_dapi_mip.png"
    assert Path(manifest["qc"]["dapi_mip_path"]).exists()


def test_export_preprocessed_channels_writes_raw_nrrd_by_default(tmp_path, monkeypatch):
    nrrd = pytest.importorskip("nrrd")
    channels = [
        ChannelInfo(index=0, gene="gene_a", wavelength_nm=488),
        ChannelInfo(index=1, gene="DAPI", wavelength_nm=740),
    ]
    metadata = StackMetadata(
        path=str(tmp_path / "sample_gene_a_488.lsm"),
        axes="ZCYX",
        shape=(2, 2, 3, 4),
        dtype="uint8",
        channels=channels,
    )
    data = np.arange(2 * 2 * 3 * 4, dtype=np.uint8).reshape(metadata.shape)

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
            crop_center_yx=(1, 2),
        ),
        tmp_path,
        crop_size_px=2,
    )

    out_path = output_dir / "sample_gene_a_488_gene_a_488nm_preprocessed.nrrd"
    exported, header = nrrd.read(str(out_path), index_order="C")

    assert header["encoding"] == "raw"
    assert exported.dtype == np.uint8
    np.testing.assert_array_equal(exported, data[:, 0, 0:2, 1:3])


def test_export_preprocessed_channels_writes_rotated_itk_readable_nrrd(
    tmp_path, monkeypatch
):
    nrrd = pytest.importorskip("nrrd")
    sitk = pytest.importorskip("SimpleITK")
    channels = [ChannelInfo(index=0, gene="DAPI", wavelength_nm=740)]
    metadata = StackMetadata(
        path=str(tmp_path / "sample_dapi_740.lsm"),
        axes="ZCYX",
        shape=(2, 1, 5, 6),
        dtype="uint16",
        channels=channels,
        voxel_size_x_m=1e-6,
        voxel_size_y_m=2e-6,
        voxel_size_z_m=3e-6,
    )
    channel_stack = np.zeros((2, 5, 6), dtype=np.uint16)
    channel_stack[:, 0, 1:5] = 100
    channel_stack[:, 3, 5] = 250
    channel_stack[1, 4, 0] = 500
    data = channel_stack[:, np.newaxis, :, :]

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
            rotation_degrees=90.0,
            crop_center_yx=None,
        ),
        tmp_path,
        interpolation="nearest",
        expand_canvas=True,
        crop_size_px=7,
    )

    out_path = output_dir / "sample_dapi_740_DAPI_740nm_preprocessed.nrrd"
    expected = crop_square_zyx(
        rotate_stack_zyx(
            channel_stack,
            -90.0,
            interpolation="nearest",
            expand_canvas=True,
        ),
        None,
        7,
    )
    wrong_sign = crop_square_zyx(
        rotate_stack_zyx(
            channel_stack,
            90.0,
            interpolation="nearest",
            expand_canvas=True,
        ),
        None,
        7,
    )
    unrotated = crop_square_zyx(channel_stack, None, 7)
    exported, header = nrrd.read(str(out_path), index_order="C")
    default_exported, _ = nrrd.read(str(out_path))
    itk_image = sitk.ReadImage(str(out_path))
    itk_array = sitk.GetArrayFromImage(itk_image)

    np.testing.assert_array_equal(exported, expected)
    assert not np.array_equal(exported, unrotated)
    assert not np.array_equal(exported, wrong_sign)
    assert default_exported.shape == (7, 7, 2)
    np.testing.assert_array_equal(np.transpose(default_exported, (2, 1, 0)), expected)
    assert list(header["sizes"]) == [7, 7, 2]
    assert header["rotation_degrees"] == "90.0"
    assert header["applied_rotation_degrees"] == "-90.0"
    assert itk_image.GetSize() == (7, 7, 2)
    assert itk_image.GetSpacing() == (1.0, 2.0, 3.0)
    np.testing.assert_array_equal(itk_array, expected)
    manifest = json.loads((output_dir / "preprocess_manifest.json").read_text())
    qc_path = Path(manifest["qc"]["dapi_mip_path"])
    assert qc_path.name == "preprocess_qc_dapi_mip.png"
    assert manifest["rotation_degrees"] == 90.0
    assert manifest["applied_rotation_degrees"] == -90.0
    assert manifest["qc"]["rotation_degrees"] == 90.0
    assert manifest["qc"]["applied_rotation_degrees"] == -90.0
    qc_image = _read_grayscale_png(qc_path)
    assert qc_image.shape == (7, 7)
    assert qc_image.max() > qc_image.min()


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


def _read_grayscale_png(path: Path) -> np.ndarray:
    data = path.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    offset = 8
    width = height = None
    compressed = bytearray()
    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        offset += length + 12
        if kind == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
            assert bit_depth == 8
            assert color_type == 0
            assert interlace == 0
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            break

    assert width is not None
    assert height is not None
    raw = zlib.decompress(bytes(compressed))
    rows = []
    row_length = int(width)
    for row_index in range(int(height)):
        start = row_index * (row_length + 1)
        assert raw[start] == 0
        rows.append(np.frombuffer(raw[start + 1 : start + 1 + row_length], dtype=np.uint8))
    return np.vstack(rows)
