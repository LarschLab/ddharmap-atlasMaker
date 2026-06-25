from __future__ import annotations

import nrrd
import numpy as np

from brain_atlas_viewer.masks import (
    Contour,
    MaskSession,
    RefinedContour,
    apply_lasso_to_slice,
    apply_lasso_to_refined_slice,
    extract_bilateral_refined_contours,
    fill_holes_2d_by_slice,
    fill_holes_3d,
    generate_candidate_mask,
    interpolate_axial_contours,
    orient_display_mask_for_disk,
    refined_contours_to_mask,
    remove_small_components_by_volume,
    save_session,
    load_or_create_session,
    write_mask_nrrd,
)


def square(z: int, x0: int, y0: int, x1: int, y1: int) -> Contour:
    return Contour(
        z=z,
        points=((x0, y0), (x1, y0), (x1, y1), (x0, y1)),
    )


def test_multiple_axial_contours_on_same_key_slice_are_combined():
    roi = interpolate_axial_contours(
        [
            square(1, 1, 1, 3, 3),
            square(1, 6, 1, 8, 3),
        ],
        (3, 10, 10),
    )

    assert roi[1, 2, 2]
    assert roi[1, 2, 7]
    assert not roi[1, 2, 5]


def test_axial_contours_interpolate_between_key_slices():
    roi = interpolate_axial_contours(
        [
            square(0, 2, 2, 6, 6),
            square(4, 2, 2, 6, 6),
        ],
        (5, 10, 10),
    )

    assert roi[:, 4, 4].all()
    assert not roi[:, 0, 0].any()


def test_candidate_uses_per_stack_thresholds_and_agreement_inside_roi_only():
    roi = np.zeros((2, 3, 3), dtype=bool)
    roi[:, 1, 1] = True
    roi[:, 1, 2] = True
    volume_a = np.zeros((2, 3, 3), dtype=np.float32)
    volume_b = np.zeros((2, 3, 3), dtype=np.float32)
    volume_c = np.zeros((2, 3, 3), dtype=np.float32)
    volume_a[:, 1, 1] = 8
    volume_b[:, 1, 1] = 11
    volume_c[:, 1, 1] = 1
    volume_a[:, 1, 2] = 8
    volume_b[:, 1, 2] = 2
    volume_c[:, 1, 2] = 4
    volume_a[:, 0, 0] = 100
    volume_b[:, 0, 0] = 100

    candidate = generate_candidate_mask(
        roi,
        {"a": volume_a, "b": volume_b, "c": volume_c},
        {"a": 5, "b": 10, "c": 5},
        agreement_count=2,
    )

    assert candidate[:, 1, 1].all()
    assert not candidate[:, 1, 2].any()
    assert not candidate[:, 0, 0].any()


def test_final_lasso_add_and_subtract_apply_to_current_slice():
    mask = np.zeros((2, 8, 8), dtype=bool)
    added = apply_lasso_to_slice(
        mask,
        1,
        [[1, 1], [5, 1], [5, 5], [1, 5]],
        "add",
    )
    subtracted = apply_lasso_to_slice(
        added,
        1,
        [[2, 2], [4, 2], [4, 4], [2, 4]],
        "subtract",
    )

    assert added[1, 3, 3]
    assert not added[0].any()
    assert not subtracted[1, 3, 3]
    assert subtracted[1, 1, 1]


def test_remove_small_components_uses_physical_volume():
    mask = np.zeros((1, 5, 8), dtype=bool)
    mask[0, 1, 1] = True
    mask[0, 1:4, 4:7] = True

    cleaned = remove_small_components_by_volume(
        mask,
        {"x": 2.0, "y": 2.0, "z": 5.0},
        minimum_um3=100.0,
    )

    assert not cleaned[0, 1, 1]
    assert cleaned[0, 2, 5]


def test_fill_holes_2d_by_slice_fills_open_3d_tunnels():
    mask = np.ones((3, 7, 7), dtype=bool)
    mask[:, 2:5, 2:5] = False
    mask[0, 3, 3] = True

    filled_3d = fill_holes_3d(mask)
    filled_2d = fill_holes_2d_by_slice(mask)

    assert not filled_3d[1, 3, 3]
    assert filled_2d[:, 3, 3].all()


def test_bilateral_refinement_discards_fragments_and_mirrors_unmatched_component():
    mask = np.zeros((1, 20, 30), dtype=bool)
    mask[0, 6:14, 4:10] = True
    mask[0, 2:4, 12:14] = True

    contours, metadata = extract_bilateral_refined_contours(
        mask,
        midline_x=15,
        min_area_px=10,
        min_component_fraction=0.25,
        smoothing_px=1,
        simplify_px=0.5,
    )

    assert {contour.side for contour in contours} == {"left", "right"}
    assert {contour.status for contour in contours} == {"observed", "inferred"}
    assert metadata["inferred_refined_contour_count"] == 1
    inferred = next(contour for contour in contours if contour.status == "inferred")
    assert inferred.source_side == "left"
    assert all(x > 15 for x, _y in inferred.points)
    assert metadata["discarded_component_count"] == 1


def test_bilateral_refinement_keeps_all_eligible_components_per_side():
    mask = np.zeros((1, 30, 40), dtype=bool)
    mask[0, 4:8, 2:6] = True
    mask[0, 10:20, 8:18] = True
    mask[0, 10:20, 24:34] = True
    mask[0, 4:8, 34:38] = True

    contours, metadata = extract_bilateral_refined_contours(
        mask,
        midline_x=20,
        min_area_px=5,
        min_component_fraction=0.1,
        smoothing_px=0,
        simplify_px=0,
    )
    refined = refined_contours_to_mask(contours, mask.shape)

    assert len(contours) == 4
    assert {contour.status for contour in contours} == {"averaged"}
    assert refined[0, 15, 12]
    assert refined[0, 15, 28]
    assert refined[0, 5, 4]
    assert refined[0, 5, 36]
    assert metadata["discarded_component_count"] == 0


def test_bilateral_refinement_filters_components_below_area_threshold():
    mask = np.zeros((1, 30, 40), dtype=bool)
    mask[0, 4:6, 2:4] = True
    mask[0, 10:20, 8:18] = True
    mask[0, 10:20, 24:34] = True

    contours, metadata = extract_bilateral_refined_contours(
        mask,
        midline_x=20,
        min_area_px=5,
        min_component_fraction=0.1,
        smoothing_px=0,
        simplify_px=0,
    )
    refined = refined_contours_to_mask(contours, mask.shape)

    assert len(contours) == 2
    assert refined[0, 15, 12]
    assert refined[0, 15, 28]
    assert not refined[0, 5, 3]
    assert metadata["discarded_component_count"] == 1


def test_bilateral_refinement_averages_left_and_right_shapes():
    mask = np.zeros((1, 30, 50), dtype=bool)
    mask[0, 10:20, 8:14] = True
    mask[0, 8:22, 33:39] = True

    contours, metadata = extract_bilateral_refined_contours(
        mask,
        midline_x=25,
        min_area_px=5,
        min_component_fraction=0.2,
        smoothing_px=0,
        simplify_px=0,
        symmetry_mode="average",
    )
    refined = refined_contours_to_mask(contours, mask.shape)
    left_area = int(refined[0, :, :25].sum())
    right_area = int(refined[0, :, 25:].sum())

    assert {contour.status for contour in contours} == {"averaged"}
    assert abs(left_area - right_area) <= 2
    assert metadata["symmetry_mode"] == "average"


def test_z_smoothing_can_bridge_missing_slice_guidance():
    mask = np.zeros((5, 30, 50), dtype=bool)
    mask[1, 10:20, 8:14] = True
    mask[1, 10:20, 36:42] = True
    mask[3, 10:20, 8:14] = True
    mask[3, 10:20, 36:42] = True

    contours, metadata = extract_bilateral_refined_contours(
        mask,
        midline_x=25,
        min_area_px=5,
        min_component_fraction=0.2,
        smoothing_px=0,
        simplify_px=0,
        symmetry_mode="average",
        z_smoothing_slices=1.0,
    )

    assert 2 in {contour.z for contour in contours}
    assert metadata["z_smoothing_slices"] == 1.0


def test_refined_lasso_edits_current_slice_then_reextracts_contours():
    mask = np.zeros((2, 20, 30), dtype=bool)
    mask[1, 6:12, 4:10] = True
    contours, _metadata = extract_bilateral_refined_contours(
        mask,
        midline_x=15,
        min_area_px=5,
        min_component_fraction=0.25,
        smoothing_px=0,
        simplify_px=0,
    )

    edited = apply_lasso_to_refined_slice(
        contours,
        mask.shape,
        1,
        [[20, 6], [25, 6], [25, 12], [20, 12]],
        "add",
        midline_x=15,
        min_area_px=5,
        min_component_fraction=0.25,
        smoothing_px=0,
        simplify_px=0,
    )

    assert any(contour.side == "right" and contour.status == "averaged" for contour in edited)
    assert not any(contour.side == "right" and contour.status == "inferred" for contour in edited)


def test_write_mask_nrrd_uses_reference_header_and_disk_orientation(tmp_path):
    reference = tmp_path / "reference.nrrd"
    output = tmp_path / "mask.nrrd"
    nrrd.write(
        str(reference),
        np.zeros((2, 3, 4), dtype=np.float32),
        header={
            "space directions": [
                [0.5, 0.0, 0.0],
                [0.0, 0.75, 0.0],
                [0.0, 0.0, 2.0],
            ],
            "space units": ["microns", "microns", "microns"],
        },
        index_order="C",
    )
    display_mask = np.zeros((2, 3, 4), dtype=bool)
    display_mask[0, 1, 2] = True

    write_mask_nrrd(output, display_mask, reference)
    data, header = nrrd.read(str(output), index_order="C")

    np.testing.assert_array_equal(data, orient_display_mask_for_disk(display_mask))
    assert data.dtype == np.uint8
    assert int(data.max()) == 1
    assert np.allclose(header["space directions"][0], [0.5, 0.0, 0.0])


def test_save_and_load_refined_contours_sidecar(tmp_path):
    reference = tmp_path / "reference.nrrd"
    nrrd.write(str(reference), np.zeros((2, 8, 8), dtype=np.float32), index_order="C")
    session = MaskSession(
        mask_name="region",
        marker="gbx2",
        output_dir=tmp_path,
        dimensions={"x": 8, "y": 8, "z": 2},
        spacing={"x": 1.0, "y": 1.0, "z": 2.0},
        reference_path=reference,
        marker_layer_ids=["a", "b"],
        refined_contours=[
            RefinedContour(
                z=1,
                side="left",
                status="inferred",
                source_side="right",
                points=((1, 1), (3, 1), (3, 3), (1, 3)),
            )
        ],
        refined_applied_to_final=False,
        midline_x=4.0,
        refinement={"source": "candidate", "smoothing_px": 2.0},
    )

    save_session(session)
    loaded = load_or_create_session(
        tmp_path,
        "region",
        "gbx2",
        {"x": 8, "y": 8, "z": 2},
        {"x": 1.0, "y": 1.0, "z": 2.0},
        reference,
        ["a", "b"],
    )

    assert loaded.midline_x == 4.0
    assert not loaded.refined_applied_to_final
    assert loaded.refinement["source"] == "candidate"
    assert len(loaded.refined_contours) == 1
    assert loaded.refined_contours[0].status == "inferred"
