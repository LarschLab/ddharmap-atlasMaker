from pathlib import Path
import json
import struct
import zlib

import numpy as np
import pytest

from brain_atlas_preprocess.io import (
    StackFormatError,
    StackMetadata,
    build_channel_mapping,
    build_channel_mapping_suggestions,
    crop_square_zyx,
    export_preprocessed_channels,
    infer_channel_mapping,
    load_channel_mip,
    load_channel_mips,
    load_dapi_mip,
    load_labeled_channel_mip,
    make_file_state,
    parse_gene_wavelength_pairs,
    preview_angle_to_export_angle,
    read_lsm_metadata,
    read_unlabeled_lsm_metadata,
    rotate_stack_zyx,
    validate_channel_mapping,
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


def test_channel_mapping_suggestions_fill_unexplained_channels():
    channels = build_channel_mapping_suggestions(
        "20260312_f02_arxa_488_Stitch.lsm",
        channel_count=3,
    )

    assert [(c.index, c.gene, c.wavelength_nm) for c in channels] == [
        (0, "arxa", 488),
        (1, "channel_2", 2),
        (2, "DAPI", 740),
    ]


def test_validate_channel_mapping_rejects_duplicate_output_labels():
    with pytest.raises(ValueError, match="Duplicate output channel label"):
        validate_channel_mapping(
            [
                ChannelInfo(index=0, gene="bridge", wavelength_nm=740),
                ChannelInfo(index=1, gene="bridge", wavelength_nm=740),
            ],
            channel_count=2,
        )


def test_infer_channel_mapping_uses_lsm_metadata_order_and_filename_genes():
    inference = infer_channel_mapping(
        "L758_f02_H2B-GC6s_488_sst1_1_546_pth2_647.lsm",
        3,
        _lsm_metadata_488_546_647(),
    )

    assert not inference.requires_confirmation
    assert inference.messages == ()
    assert [(c.index, c.gene, c.wavelength_nm) for c in inference.channels] == [
        (0, "H2B-GC6s", 488),
        (1, "sst1_1", 546),
        (2, "pth2", 647),
    ]


def test_infer_channel_mapping_uses_lsm_metadata_for_dapi_stack_order():
    inference = infer_channel_mapping(
        "trha_488_kiss2_647_DAPI_740nm_f03_Stitch.lsm",
        3,
        _lsm_metadata_488_647_dapi(),
    )

    assert not inference.requires_confirmation
    assert [(c.index, c.gene, c.wavelength_nm) for c in inference.channels] == [
        (0, "trha", 488),
        (1, "kiss2", 647),
        (2, "DAPI", 740),
    ]


def test_infer_channel_mapping_requires_confirmation_for_filename_metadata_conflict():
    inference = infer_channel_mapping(
        "trha_546_kiss2_647_DAPI_740nm_f03_Stitch.lsm",
        3,
        _lsm_metadata_488_647_dapi(),
    )

    assert inference.requires_confirmation
    assert [(c.index, c.gene, c.wavelength_nm) for c in inference.channels] == [
        (0, "trha", 488),
        (1, "kiss2", 647),
        (2, "DAPI", 740),
    ]
    assert "trha_546nm" in " ".join(inference.messages)
    assert "488 nm" in " ".join(inference.messages)


def test_infer_channel_mapping_falls_back_to_filename_suggestions_without_metadata():
    inference = infer_channel_mapping(
        "sample_gene_a_488.lsm",
        3,
        {},
    )

    assert inference.requires_confirmation
    assert [(c.index, c.gene, c.wavelength_nm) for c in inference.channels] == [
        (0, "gene_a", 488),
        (1, "channel_2", 2),
        (2, "DAPI", 740),
    ]


def test_read_lsm_metadata_autodiscovers_conflict_free_channels(monkeypatch):
    monkeypatch.setattr(
        "brain_atlas_preprocess.io.tifffile.TiffFile",
        lambda path: _FakeMetadataTiff(_lsm_metadata_488_546_647()),
    )

    metadata = read_lsm_metadata(
        "L758_f02_H2B-GC6s_488_sst1_1_546_pth2_647.lsm"
    )

    assert not metadata.channel_mapping_requires_confirmation
    assert [(c.index, c.gene, c.wavelength_nm) for c in metadata.channels] == [
        (0, "H2B-GC6s", 488),
        (1, "sst1_1", 546),
        (2, "pth2", 647),
    ]


def test_read_lsm_metadata_rejects_autodiscovered_conflict(monkeypatch):
    monkeypatch.setattr(
        "brain_atlas_preprocess.io.tifffile.TiffFile",
        lambda path: _FakeMetadataTiff(_lsm_metadata_488_647_dapi()),
    )

    with pytest.raises(StackFormatError, match="Confirm channel mapping"):
        read_lsm_metadata(
            "trha_546_kiss2_647_DAPI_740nm_f03_Stitch.lsm"
        )


def test_read_lsm_metadata_manual_channels_bypass_autodiscovery(monkeypatch):
    monkeypatch.setattr(
        "brain_atlas_preprocess.io.tifffile.TiffFile",
        lambda path: _FakeMetadataTiff(_lsm_metadata_488_647_dapi()),
    )
    channels = [
        ChannelInfo(index=0, gene="trha", wavelength_nm=546),
        ChannelInfo(index=1, gene="kiss2", wavelength_nm=647),
        ChannelInfo(index=2, gene="DAPI", wavelength_nm=740),
    ]

    metadata = read_lsm_metadata(
        "trha_546_kiss2_647_DAPI_740nm_f03_Stitch.lsm",
        channels=channels,
    )

    assert metadata.channels == channels
    assert not metadata.channel_mapping_requires_confirmation


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


def test_load_channel_mip_uses_requested_channel(monkeypatch):
    data = np.array(
        [
            [
                [[1, 2], [3, 4]],
                [[10, 1], [2, 3]],
                [[5, 5], [5, 5]],
            ],
            [
                [[9, 1], [1, 1]],
                [[4, 11], [12, 1]],
                [[6, 6], [6, 6]],
            ],
        ],
        dtype=np.uint16,
    )

    class FakePage:
        def __init__(self, plane):
            self._plane = plane

        def asarray(self):
            return self._plane

    class FakeSeries:
        axes = "ZCYX"
        shape = data.shape
        dtype = data.dtype

        @property
        def pages(self):
            return [FakePage(data[z]) for z in range(data.shape[0])]

    class FakeTiffFile:
        is_lsm = True
        lsm_metadata = {}

        def __init__(self, path):
            self.series = [FakeSeries()]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr("brain_atlas_preprocess.io.tifffile.TiffFile", FakeTiffFile)

    mip = load_channel_mip("sample_bridge_555.lsm", 1)

    np.testing.assert_array_equal(mip, np.array([[10, 11], [12, 3]], dtype=np.uint16))


def test_load_channel_mips_loads_all_channels_in_one_result(monkeypatch):
    data = np.array(
        [
            [
                [[1, 2], [3, 4]],
                [[10, 1], [2, 3]],
                [[5, 5], [5, 5]],
            ],
            [
                [[9, 1], [1, 1]],
                [[4, 11], [12, 1]],
                [[6, 7], [8, 9]],
            ],
        ],
        dtype=np.uint16,
    )

    class FakePage:
        def __init__(self, plane):
            self._plane = plane

        def asarray(self):
            return self._plane

    class FakeSeries:
        axes = "ZCYX"
        shape = data.shape
        dtype = data.dtype

        @property
        def pages(self):
            return [FakePage(data[z]) for z in range(data.shape[0])]

    class FakeTiffFile:
        is_lsm = True
        lsm_metadata = {}

        def __init__(self, path):
            self.series = [FakeSeries()]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr("brain_atlas_preprocess.io.tifffile.TiffFile", FakeTiffFile)

    mips = load_channel_mips("sample_bridge_555.lsm")

    assert sorted(mips) == [0, 1, 2]
    np.testing.assert_array_equal(mips[0], np.array([[9, 2], [3, 4]], dtype=np.uint16))
    np.testing.assert_array_equal(mips[1], np.array([[10, 11], [12, 3]], dtype=np.uint16))
    np.testing.assert_array_equal(mips[2], np.array([[6, 7], [8, 9]], dtype=np.uint16))


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
    assert header["space units"] == ["microns", "microns", "microns"]
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


def test_export_preprocessed_channels_uses_selected_bridge_for_qc(
    tmp_path, monkeypatch
):
    pytest.importorskip("nrrd")
    channels = [
        ChannelInfo(index=0, gene="bridge", wavelength_nm=555),
        ChannelInfo(index=1, gene="DAPI", wavelength_nm=740),
    ]
    metadata = StackMetadata(
        path=str(tmp_path / "sample_bridge_555.lsm"),
        axes="ZCYX",
        shape=(2, 2, 3, 3),
        dtype="uint8",
        channels=channels,
    )
    data = np.zeros(metadata.shape, dtype=np.uint8)
    data[:, 0, :, :] = np.array(
        [
            [[0, 10, 20], [30, 40, 50], [60, 70, 80]],
            [[90, 100, 110], [120, 130, 140], [150, 160, 170]],
        ],
        dtype=np.uint8,
    )
    data[:, 1, :, :] = 1

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

    def fake_read_lsm_metadata(path, *, channels=None):
        return StackMetadata(
            path=metadata.path,
            axes=metadata.axes,
            shape=metadata.shape,
            dtype=metadata.dtype,
            channels=channels or metadata.channels,
        )

    monkeypatch.setattr(
        "brain_atlas_preprocess.io.read_lsm_metadata", fake_read_lsm_metadata
    )
    monkeypatch.setattr("brain_atlas_preprocess.io.tifffile.TiffFile", FakeTiffFile)

    output_dir = export_preprocessed_channels(
        StackFileState(
            path=metadata.path,
            channels=channels,
            bridge_channel_index=0,
            rotation_degrees=0.0,
            crop_center_yx=(1, 1),
        ),
        tmp_path,
        crop_size_px=3,
    )

    manifest = json.loads((output_dir / "preprocess_manifest.json").read_text())
    assert manifest["bridge_channel"] == channels[0].to_dict()
    assert manifest["qc"]["bridge_channel"] == channels[0].to_dict()
    qc_image = _read_grayscale_png(Path(manifest["qc"]["dapi_mip_path"]))
    assert qc_image.max() > qc_image.min()


def test_export_preprocessed_channels_threaded_matches_single_worker(
    tmp_path, monkeypatch
):
    nrrd = pytest.importorskip("nrrd")
    channels = [
        ChannelInfo(index=0, gene="gene_a", wavelength_nm=546),
        ChannelInfo(index=1, gene="gene_b", wavelength_nm=488),
        ChannelInfo(index=2, gene="DAPI", wavelength_nm=740),
    ]
    metadata = StackMetadata(
        path=str(tmp_path / "sample_gene_a_546_gene_b_488.lsm"),
        axes="ZCYX",
        shape=(3, 3, 8, 9),
        dtype="uint8",
        channels=channels,
    )
    data = (np.arange(np.prod(metadata.shape), dtype=np.uint16) % 251).astype(
        np.uint8
    )
    data = data.reshape(metadata.shape)

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

    file_state = StackFileState(
        path=metadata.path,
        rotation_degrees=17.5,
        crop_center_yx=(4, 4),
    )
    single_dir = export_preprocessed_channels(
        file_state,
        tmp_path / "single",
        crop_size_px=6,
        transform_workers=1,
    )
    threaded_dir = export_preprocessed_channels(
        file_state,
        tmp_path / "threaded",
        crop_size_px=6,
        transform_workers=4,
    )

    single_manifest = json.loads((single_dir / "preprocess_manifest.json").read_text())
    threaded_manifest = json.loads(
        (threaded_dir / "preprocess_manifest.json").read_text()
    )

    assert [item["channel"] for item in threaded_manifest["output_files"]] == [
        item["channel"] for item in single_manifest["output_files"]
    ]
    for single_file, threaded_file in zip(
        single_manifest["output_files"],
        threaded_manifest["output_files"],
    ):
        single_array, _ = nrrd.read(single_file["path"], index_order="C")
        threaded_array, _ = nrrd.read(threaded_file["path"], index_order="C")
        np.testing.assert_array_equal(threaded_array, single_array)


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


def test_optional_20260525_mismatched_stack_directory_smoke():
    root = Path("/Users/ddharmap/dataProcessing/20260525_brainMapping_stitched")
    if not root.exists():
        pytest.skip("Local 20260525 stitched stack directory is not available.")

    paths = sorted(root.glob("*.lsm"))
    assert paths
    auto_count = 0
    manual_count = 0
    for path in paths:
        try:
            file_state = make_file_state(path)
            auto_count += 1
        except StackFormatError:
            metadata = read_unlabeled_lsm_metadata(path)
            channels = build_channel_mapping_suggestions(path, int(metadata.shape[1]))
            file_state = make_file_state(
                path,
                channels=channels,
                bridge_channel_index=channels[-1].index,
            )
            manual_count += 1

        bridge_index = file_state.resolved_bridge_channel_index()
        assert bridge_index is not None
        mips = load_channel_mips(file_state.path)
        assert sorted(mips) == [channel.index for channel in file_state.channels]
        for channel in file_state.channels:
            assert mips[channel.index].shape == file_state.shape[-2:]
        mip = load_labeled_channel_mip(
            file_state.path,
            file_state.channels,
            bridge_index,
        )
        assert mip.shape == file_state.shape[-2:]

    assert auto_count > 0
    assert auto_count + manual_count == len(paths)


class _FakeMetadataSeries:
    axes = "ZCYX"
    shape = (2, 3, 4, 5)
    dtype = np.dtype("uint8")


class _FakeMetadataTiff:
    is_lsm = True

    def __init__(self, lsm_metadata):
        self.series = [_FakeMetadataSeries()]
        self.lsm_metadata = lsm_metadata

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


def _lsm_metadata_488_546_647():
    return {
        "ChannelWavelength": np.array(
            [
                [4.9245e-7, 5.4207e-7],
                [5.6901e-7, 7.3500e-7],
                [5.6620e-7, 7.3507e-7],
            ]
        ),
        "ScanInformation": {
            "Tracks": [
                {
                    "DataChannels": [
                        {"Acquire": 0, "Name": "Ch1"},
                        {"Acquire": 1, "Name": "Ch2"},
                    ],
                    "DetectionChannels": [
                        {
                            "DyeName": "EGFP",
                            "SpiWavelengthStart": 492.45,
                            "SpiWavelengthStop": 542.07,
                        },
                        {
                            "DyeName": "Alexa Fluor 546",
                            "SpiWavelengthStart": 569.01,
                            "SpiWavelengthStop": 735.0,
                        },
                    ],
                    "IlluminationChannels": [
                        {"Wavelength": 561.0},
                        {"Wavelength": 488.0},
                    ],
                },
                {
                    "DataChannels": [{"Acquire": 2, "Name": "Ch1"}],
                    "DetectionChannels": [
                        {
                            "DyeName": "Alexa Fluor 647",
                            "SpiWavelengthStart": 566.2,
                            "SpiWavelengthStop": 735.07,
                        },
                    ],
                    "IlluminationChannels": [{"Wavelength": 633.0}],
                },
            ],
        },
    }


def _lsm_metadata_488_647_dapi():
    return {
        "ChannelWavelength": np.array(
            [
                [4.9595e-7, 5.7782e-7],
                [6.4651e-7, 7.3173e-7],
                [4.1170e-7, 5.5207e-7],
            ]
        ),
        "ScanInformation": {
            "Tracks": [
                {
                    "DataChannels": [
                        {"Acquire": 0, "Name": "Ch1"},
                        {"Acquire": 1, "Name": "Ch2"},
                    ],
                    "DetectionChannels": [
                        {
                            "DyeName": "Alexa Fluor 488",
                            "SpiWavelengthStart": 495.95,
                            "SpiWavelengthStop": 577.82,
                        },
                        {
                            "DyeName": "Alexa Fluor 647",
                            "SpiWavelengthStart": 646.51,
                            "SpiWavelengthStop": 731.73,
                        },
                    ],
                    "IlluminationChannels": [
                        {"Wavelength": 633.0},
                        {"Wavelength": 488.0},
                    ],
                },
                {
                    "DataChannels": [{"Acquire": 2, "Name": "Ch1"}],
                    "DetectionChannels": [
                        {
                            "DyeName": "DAPI",
                            "SpiWavelengthStart": 411.7,
                            "SpiWavelengthStop": 552.07,
                        },
                    ],
                    "IlluminationChannels": [{"Wavelength": 740.0}],
                },
            ],
        },
    }


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
