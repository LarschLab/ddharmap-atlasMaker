from __future__ import annotations

import struct

import numpy as np

from brain_atlas_viewer.app import (
    ClipStats,
    CompositeLayer,
    MARKER_PALETTE,
    assign_marker_colors,
    composite_rgb,
    compute_clip_stats,
    compute_histogram_stats,
    encode_png_rgb,
    histogram_percentile,
    normalize_plane,
    orient_volume_for_display,
    parse_window_overrides,
    plane_slice,
)


def test_plane_slice_uses_zyx_volume_coordinates():
    volume = np.arange(2 * 3 * 4, dtype=np.float32).reshape(2, 3, 4)

    np.testing.assert_array_equal(plane_slice(volume, "axial", 1), volume[1, :, :])
    np.testing.assert_array_equal(plane_slice(volume, "sagittal", 2), volume[:, :, 2])
    np.testing.assert_array_equal(plane_slice(volume, "coronal", 1), volume[:, 1, :])


def test_plane_slice_mip_matches_plane_axis():
    volume = np.arange(2 * 3 * 4, dtype=np.float32).reshape(2, 3, 4)

    np.testing.assert_array_equal(plane_slice(volume, "axial", "mip"), volume.max(axis=0))
    np.testing.assert_array_equal(
        plane_slice(volume, "sagittal", "mip"), volume.max(axis=2)
    )
    np.testing.assert_array_equal(
        plane_slice(volume, "coronal", "mip"), volume.max(axis=1)
    )


def test_orient_volume_for_display_flips_z_axis():
    volume = np.arange(2 * 3 * 4, dtype=np.float32).reshape(2, 3, 4)

    oriented = orient_volume_for_display(volume)

    np.testing.assert_array_equal(oriented[0], volume[1])
    np.testing.assert_array_equal(oriented[1], volume[0])


def test_assign_marker_colors_uses_marker_palette_not_wavelengths():
    colors = assign_marker_colors(["agrp", "pomca", "gad1b", "cort"])

    assert colors == {
        "agrp": MARKER_PALETTE[0],
        "cort": MARKER_PALETTE[1],
        "gad1b": MARKER_PALETTE[2],
        "pomca": MARKER_PALETTE[3],
    }
    assert len(set(colors.values())) == 4


def test_normalize_plane_applies_clip_brightness_and_contrast():
    plane = np.array([[0, 128, 255]], dtype=np.float32)

    normalized = normalize_plane(plane, brightness=100, contrast=100)

    assert normalized[0, 0] == 0
    assert 0.49 < normalized[0, 1] < 0.51
    assert normalized[0, 2] == 1


def test_compute_clip_stats_uses_stack_percentiles():
    volume = np.arange(1001, dtype=np.float32)

    stats = compute_clip_stats(volume)

    assert stats.minimum == 10
    assert stats.maximum == 995


def test_composite_rgb_returns_uint8_rgb_image():
    volume = np.zeros((2, 3, 4), dtype=np.float32)
    volume[:, :, 2] = 255

    image = composite_rgb(
        [CompositeLayer(volume, "#ff0000", ClipStats(0, 255))],
        "sagittal",
        2,
        brightness=100,
        contrast=100,
        opacity=1,
    )

    assert image.shape == (2, 3, 3)
    assert image.dtype == np.uint8
    assert image[:, :, 0].max() == 255
    assert image[:, :, 1].max() == 0
    assert image[:, :, 2].max() == 0


def test_histogram_stats_return_binned_counts_and_percentile_values():
    volume = np.arange(100, dtype=np.float32)

    stats = compute_histogram_stats(volume, bins=10)

    assert len(stats.counts) == 10
    assert len(stats.edges) == 11
    assert sum(stats.counts) == 100
    assert 48 <= histogram_percentile(stats.counts, stats.edges, 50) <= 51


def test_composite_rgb_applies_layer_clip_window():
    volume = np.zeros((1, 2, 3), dtype=np.float32)
    volume[:, :, 1] = 10

    wide = composite_rgb(
        [CompositeLayer(volume, "#ff0000", ClipStats(0, 20))],
        "sagittal",
        1,
        brightness=100,
        contrast=100,
        opacity=1,
    )
    narrow = composite_rgb(
        [CompositeLayer(volume, "#ff0000", ClipStats(0, 10))],
        "sagittal",
        1,
        brightness=100,
        contrast=100,
        opacity=1,
    )

    assert wide[:, :, 0].max() == 127
    assert narrow[:, :, 0].max() == 255


def test_composite_rgb_keeps_reference_visible_without_marker_layers():
    reference = np.zeros((2, 3, 4), dtype=np.float32)
    reference[1, :, :] = 255

    image = composite_rgb(
        [],
        "axial",
        1,
        brightness=100,
        contrast=100,
        opacity=1,
        reference_volume=reference,
    )

    assert image.shape == (3, 4, 3)
    assert image.dtype == np.uint8
    assert image[:, :, 0].max() > 0
    np.testing.assert_array_equal(image[:, :, 0], image[:, :, 1])
    np.testing.assert_array_equal(image[:, :, 1], image[:, :, 2])


def test_parse_window_overrides_clamps_and_skips_invalid_values():
    windows = parse_window_overrides(
        "layer-a:2.5:98.5,layer-b:-1:101,bad,layer-c:4:not-a-number,layer-d:8:3"
    )

    assert windows == {"layer-a": (2.5, 98.5), "layer-b": (0.0, 100.0)}


def test_encode_png_rgb_writes_png_dimensions():
    image = np.zeros((3, 5, 3), dtype=np.uint8)

    payload = encode_png_rgb(image)

    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", payload[16:24])
    assert (width, height) == (5, 3)
