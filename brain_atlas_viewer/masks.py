from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import nrrd
import numpy as np
from scipy import ndimage
from skimage.draw import polygon as raster_polygon
from skimage import measure


@dataclass(frozen=True)
class RefinedContour:
    z: int
    side: str
    status: str
    points: tuple[tuple[float, float], ...]
    source_side: str | None = None
    discarded_components: int = 0

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "z": self.z,
            "side": self.side,
            "status": self.status,
            "points": [[x, y] for x, y in self.points],
            "discarded_components": self.discarded_components,
        }
        if self.source_side:
            payload["source_side"] = self.source_side
        return payload

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "RefinedContour":
        return cls(
            z=int(payload["z"]),
            side=str(payload.get("side", "")),
            status=str(payload.get("status", "observed")),
            points=tuple((float(x), float(y)) for x, y in payload["points"]),
            source_side=(
                None
                if payload.get("source_side") in (None, "")
                else str(payload.get("source_side"))
            ),
            discarded_components=int(payload.get("discarded_components", 0)),
        )


@dataclass(frozen=True)
class Contour:
    z: int
    points: tuple[tuple[float, float], ...]

    def to_json(self) -> dict[str, Any]:
        return {"z": self.z, "points": [[x, y] for x, y in self.points]}

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "Contour":
        return cls(
            z=int(payload["z"]),
            points=tuple((float(x), float(y)) for x, y in payload["points"]),
        )


@dataclass
class MaskSession:
    mask_name: str
    marker: str
    output_dir: Path
    dimensions: dict[str, int]
    spacing: dict[str, float]
    reference_path: Path
    marker_layer_ids: list[str]
    contours: list[Contour] = field(default_factory=list)
    refined_contours: list[RefinedContour] = field(default_factory=list)
    thresholds: dict[str, float] = field(default_factory=dict)
    agreement_count: int = 1
    rationale: str = ""
    final_mask: np.ndarray | None = None
    candidate_mask: np.ndarray | None = None
    refined_applied_to_final: bool = False
    midline_x: float | None = None
    refinement: dict[str, Any] = field(default_factory=dict)
    outside_roi_additions: bool = False
    dirty: bool = False

    @property
    def shape_zyx(self) -> tuple[int, int, int]:
        return (
            int(self.dimensions["z"]),
            int(self.dimensions["y"]),
            int(self.dimensions["x"]),
        )

    @property
    def contour_path(self) -> Path:
        return self.output_dir / f"{self.mask_name}_roi_contours.json"

    @property
    def provenance_path(self) -> Path:
        return self.output_dir / f"{self.mask_name}_provenance.json"

    @property
    def refined_contour_path(self) -> Path:
        return self.output_dir / f"{self.mask_name}_refined_contours.json"

    @property
    def mask_path(self) -> Path:
        return self.output_dir / f"{self.mask_name}_mask.nrrd"

    def marker_warning(self) -> str | None:
        if len(self.marker_layer_ids) < 2:
            return (
                f"Only {len(self.marker_layer_ids)} stack matches marker "
                f"{self.marker!r}; cross-stack agreement is unavailable."
            )
        return None

    def roi_mask(self) -> np.ndarray:
        return interpolate_axial_contours(self.contours, self.shape_zyx)

    def to_json(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "mask_name": self.mask_name,
            "marker": self.marker,
            "output_dir": str(self.output_dir),
            "dimensions": self.dimensions,
            "spacing": self.spacing,
            "reference_path": str(self.reference_path),
            "marker_layer_ids": self.marker_layer_ids,
            "contours": [contour.to_json() for contour in self.contours],
            "refined_contours": [
                contour.to_json() for contour in self.refined_contours
            ],
            "has_refined": bool(self.refined_contours),
            "refined_applied_to_final": self.refined_applied_to_final,
            "midline_x": self.midline_x,
            "refinement": self.refinement,
            "thresholds": self.thresholds,
            "agreement_count": self.agreement_count,
            "rationale": self.rationale,
            "dirty": self.dirty,
            "has_candidate": self.candidate_mask is not None,
            "has_final": self.final_mask is not None,
            "warning": self.marker_warning(),
            "paths": {
                "mask": str(self.mask_path),
                "roi_contours": str(self.contour_path),
                "refined_contours": str(self.refined_contour_path),
                "provenance": str(self.provenance_path),
            },
        }


def load_or_create_session(
    output_dir: Path,
    mask_name: str,
    marker: str,
    dimensions: dict[str, int],
    spacing: dict[str, float],
    reference_path: Path,
    marker_layer_ids: list[str],
) -> MaskSession:
    output_dir.mkdir(parents=True, exist_ok=True)
    session = MaskSession(
        mask_name=mask_name,
        marker=marker,
        output_dir=output_dir,
        dimensions=dimensions,
        spacing=spacing,
        reference_path=reference_path,
        marker_layer_ids=marker_layer_ids,
        agreement_count=max(1, min(2, len(marker_layer_ids))),
    )
    if session.contour_path.exists():
        payload = json.loads(session.contour_path.read_text())
        session.contours = [
            Contour.from_json(item) for item in payload.get("contours", [])
        ]
    if session.refined_contour_path.exists():
        payload = json.loads(session.refined_contour_path.read_text())
        session.refined_contours = [
            RefinedContour.from_json(item)
            for item in payload.get("refined_contours", [])
        ]
        session.refined_applied_to_final = bool(
            payload.get("applied_to_final", False)
        )
        raw_midline = payload.get("midline_x")
        session.midline_x = None if raw_midline is None else float(raw_midline)
        session.refinement = dict(payload.get("refinement", {}))
    if session.provenance_path.exists():
        payload = json.loads(session.provenance_path.read_text())
        session.thresholds = {
            str(key): float(value)
            for key, value in payload.get("thresholds", {}).items()
        }
        session.agreement_count = int(
            payload.get("agreement_count", session.agreement_count)
        )
        session.rationale = str(payload.get("rationale", ""))
        session.outside_roi_additions = bool(payload.get("outside_roi_additions", False))
        if session.midline_x is None and payload.get("midline_x") is not None:
            session.midline_x = float(payload["midline_x"])
        if not session.refinement and isinstance(payload.get("refinement"), dict):
            session.refinement = dict(payload["refinement"])
    if session.mask_path.exists():
        data, _header = nrrd.read(str(session.mask_path), index_order="C")
        final = orient_disk_mask_for_display(np.asarray(data, dtype=np.uint8))
        if final.shape == session.shape_zyx:
            session.final_mask = final > 0
    return session


def save_session(session: MaskSession) -> None:
    session.output_dir.mkdir(parents=True, exist_ok=True)
    contour_payload = {
        "mask_name": session.mask_name,
        "marker": session.marker,
        "axis": "z",
        "plane": "axial",
        "contours": [contour.to_json() for contour in session.contours],
    }
    session.contour_path.write_text(json.dumps(contour_payload, indent=2) + "\n")
    refined_payload = {
        "mask_name": session.mask_name,
        "marker": session.marker,
        "axis": "z",
        "plane": "axial",
        "midline_x": session.midline_x,
        "applied_to_final": session.refined_applied_to_final,
        "refinement": session.refinement,
        "refined_contours": [
            contour.to_json() for contour in session.refined_contours
        ],
    }
    session.refined_contour_path.write_text(
        json.dumps(refined_payload, indent=2) + "\n"
    )
    inferred_count = sum(
        1 for contour in session.refined_contours if contour.status == "inferred"
    )
    provenance = {
        "mask_name": session.mask_name,
        "marker": session.marker,
        "created_or_updated_utc": datetime.now(timezone.utc).isoformat(),
        "reference_path": str(session.reference_path),
        "dimensions": session.dimensions,
        "spacing": session.spacing,
        "marker_layer_ids": session.marker_layer_ids,
        "thresholds": session.thresholds,
        "agreement_count": session.agreement_count,
        "agreement_fraction": (
            session.agreement_count / len(session.marker_layer_ids)
            if session.marker_layer_ids
            else None
        ),
        "midline_x": session.midline_x,
        "refinement": {
            **session.refinement,
            "refined_contour_count": len(session.refined_contours),
            "inferred_refined_contour_count": inferred_count,
            "applied_to_final": session.refined_applied_to_final,
        },
        "rationale": session.rationale,
        "outside_roi_additions": session.outside_roi_additions,
        "warning": session.marker_warning(),
    }
    session.provenance_path.write_text(json.dumps(provenance, indent=2) + "\n")
    if session.final_mask is not None:
        write_mask_nrrd(session.mask_path, session.final_mask, session.reference_path)
    session.dirty = False


def write_mask_nrrd(path: Path, display_mask: np.ndarray, reference_path: Path) -> None:
    header = dict(nrrd.read_header(str(reference_path)))
    disk_mask = orient_display_mask_for_disk(display_mask).astype(np.uint8, copy=False)
    header.pop("sizes", None)
    header.pop("type", None)
    nrrd.write(str(path), disk_mask, header=header, index_order="C")


def orient_display_mask_for_disk(mask: np.ndarray) -> np.ndarray:
    return np.flip(mask, axis=0).copy()


def orient_disk_mask_for_display(mask: np.ndarray) -> np.ndarray:
    return np.flip(mask, axis=0).copy()


def interpolate_axial_contours(
    contours: list[Contour],
    shape_zyx: tuple[int, int, int],
) -> np.ndarray:
    z_size, y_size, x_size = shape_zyx
    masks_by_z: dict[int, np.ndarray] = {}
    for contour in contours:
        if contour.z < 0 or contour.z >= z_size:
            continue
        masks_by_z.setdefault(contour.z, np.zeros((y_size, x_size), dtype=bool))
        masks_by_z[contour.z] |= rasterize_contour(contour, (y_size, x_size))
    volume = np.zeros(shape_zyx, dtype=bool)
    if not masks_by_z:
        return volume
    key_zs = sorted(masks_by_z)
    for z in key_zs:
        volume[z] = masks_by_z[z]
    for left, right in zip(key_zs, key_zs[1:], strict=False):
        if right <= left + 1:
            continue
        left_field = signed_distance(masks_by_z[left])
        right_field = signed_distance(masks_by_z[right])
        span = right - left
        for z in range(left + 1, right):
            t = (z - left) / span
            volume[z] = ((1.0 - t) * left_field + t * right_field) >= 0
    return volume


def rasterize_contour(contour: Contour, shape_yx: tuple[int, int]) -> np.ndarray:
    if len(contour.points) < 3:
        return np.zeros(shape_yx, dtype=bool)
    xs = np.array([point[0] for point in contour.points], dtype=float)
    ys = np.array([point[1] for point in contour.points], dtype=float)
    rr, cc = raster_polygon(ys, xs, shape=shape_yx)
    mask = np.zeros(shape_yx, dtype=bool)
    mask[rr, cc] = True
    return mask


def signed_distance(mask: np.ndarray) -> np.ndarray:
    mask = np.asarray(mask, dtype=bool)
    inside = ndimage.distance_transform_edt(mask)
    outside = ndimage.distance_transform_edt(~mask)
    return inside - outside


def generate_candidate_mask(
    roi_mask: np.ndarray,
    volumes_by_layer: dict[str, np.ndarray],
    thresholds: dict[str, float],
    agreement_count: int,
) -> np.ndarray:
    roi = np.asarray(roi_mask, dtype=bool)
    count = np.zeros(roi.shape, dtype=np.uint16)
    for layer_id, volume in volumes_by_layer.items():
        threshold = thresholds.get(layer_id)
        if threshold is None:
            continue
        if volume.shape != roi.shape:
            raise ValueError(
                f"Volume {layer_id} shape {volume.shape} does not match ROI {roi.shape}"
            )
        count += np.asarray(volume >= float(threshold), dtype=np.uint16)
    required = max(1, int(agreement_count))
    return roi & (count >= required)


def fill_holes_3d(mask: np.ndarray) -> np.ndarray:
    return ndimage.binary_fill_holes(np.asarray(mask, dtype=bool))


def fill_holes_2d_by_slice(mask: np.ndarray) -> np.ndarray:
    filled = np.asarray(mask, dtype=bool).copy()
    for z in range(filled.shape[0]):
        filled[z] = ndimage.binary_fill_holes(filled[z])
    return filled


def remove_small_components_by_volume(
    mask: np.ndarray,
    spacing: dict[str, float],
    minimum_um3: float,
) -> np.ndarray:
    voxel_volume = float(spacing["x"]) * float(spacing["y"]) * float(spacing["z"])
    minimum_voxels = max(1, int(np.ceil(float(minimum_um3) / max(voxel_volume, 1e-9))))
    labels, count = ndimage.label(np.asarray(mask, dtype=bool))
    if count == 0:
        return np.zeros_like(mask, dtype=bool)
    sizes = np.bincount(labels.ravel())
    keep = sizes >= minimum_voxels
    keep[0] = False
    return keep[labels]


def apply_lasso_to_slice(
    mask: np.ndarray,
    z: int,
    points: list[list[float]],
    mode: str,
) -> np.ndarray:
    next_mask = np.asarray(mask, dtype=bool).copy()
    contour = Contour(z=int(z), points=tuple((float(x), float(y)) for x, y in points))
    stroke = rasterize_contour(contour, next_mask.shape[1:])
    if mode == "subtract":
        next_mask[z] &= ~stroke
    elif mode == "add":
        next_mask[z] |= stroke
    else:
        raise ValueError(f"Unknown edit mode: {mode}")
    return next_mask


def refined_contours_to_mask(
    contours: list[RefinedContour],
    shape_zyx: tuple[int, int, int],
) -> np.ndarray:
    z_size, y_size, x_size = shape_zyx
    mask = np.zeros(shape_zyx, dtype=bool)
    for contour in contours:
        if contour.z < 0 or contour.z >= z_size:
            continue
        roi_contour = Contour(z=contour.z, points=contour.points)
        mask[contour.z] |= rasterize_contour(roi_contour, (y_size, x_size))
    return mask


def apply_lasso_to_refined_slice(
    contours: list[RefinedContour],
    shape_zyx: tuple[int, int, int],
    z: int,
    points: list[list[float]],
    mode: str,
    *,
    midline_x: float,
    min_area_px: int,
    min_component_fraction: float,
    smoothing_px: float,
    simplify_px: float,
    symmetry_mode: str = "average",
) -> list[RefinedContour]:
    z = int(z)
    current = refined_contours_to_mask(contours, shape_zyx)
    edited = apply_lasso_to_slice(current, z, points, mode)
    slice_contours, _metadata = extract_bilateral_refined_contours_from_slice(
        edited[z],
        z,
        midline_x=midline_x,
        min_area_px=min_area_px,
        min_component_fraction=min_component_fraction,
        smoothing_px=smoothing_px,
        simplify_px=simplify_px,
        symmetry_mode=symmetry_mode,
    )
    return [contour for contour in contours if contour.z != z] + slice_contours


def extract_bilateral_refined_contours(
    mask: np.ndarray,
    *,
    midline_x: float,
    min_area_px: int,
    min_component_fraction: float,
    smoothing_px: float,
    simplify_px: float,
    symmetry_mode: str = "average",
    z_smoothing_slices: float = 0.0,
) -> tuple[list[RefinedContour], dict[str, Any]]:
    mask = np.asarray(mask, dtype=bool)
    contours, metadata = _extract_bilateral_refined_contours_no_z_smoothing(
        mask,
        midline_x=midline_x,
        min_area_px=min_area_px,
        min_component_fraction=min_component_fraction,
        smoothing_px=smoothing_px,
        simplify_px=simplify_px,
        symmetry_mode=symmetry_mode,
    )
    if z_smoothing_slices > 0 and contours:
        refined_mask = refined_contours_to_mask(contours, mask.shape)
        smoothed = ndimage.gaussian_filter(
            refined_mask.astype(np.float32),
            sigma=(float(z_smoothing_slices), 0.0, 0.0),
        ) >= 0.25
        contours, metadata = _extract_bilateral_refined_contours_no_z_smoothing(
            smoothed,
            midline_x=midline_x,
            min_area_px=min_area_px,
            min_component_fraction=min_component_fraction,
            smoothing_px=smoothing_px,
            simplify_px=simplify_px,
            symmetry_mode=symmetry_mode,
        )
    metadata["z_smoothing_slices"] = float(z_smoothing_slices)
    return contours, metadata


def _extract_bilateral_refined_contours_no_z_smoothing(
    mask: np.ndarray,
    *,
    midline_x: float,
    min_area_px: int,
    min_component_fraction: float,
    smoothing_px: float,
    simplify_px: float,
    symmetry_mode: str,
) -> tuple[list[RefinedContour], dict[str, Any]]:
    contours: list[RefinedContour] = []
    slices_with_signal = 0
    inferred = 0
    discarded = 0
    for z in range(mask.shape[0]):
        if not mask[z].any():
            continue
        slices_with_signal += 1
        slice_contours, slice_metadata = extract_bilateral_refined_contours_from_slice(
            mask[z],
            z,
            midline_x=midline_x,
            min_area_px=min_area_px,
            min_component_fraction=min_component_fraction,
            smoothing_px=smoothing_px,
            simplify_px=simplify_px,
            symmetry_mode=symmetry_mode,
        )
        contours.extend(slice_contours)
        inferred += int(slice_metadata["inferred_count"])
        discarded += int(slice_metadata["discarded_components"])
    metadata = {
        "source_slices_with_signal": slices_with_signal,
        "refined_contour_count": len(contours),
        "inferred_refined_contour_count": inferred,
        "discarded_component_count": discarded,
        "midline_x": midline_x,
        "min_area_px": int(min_area_px),
        "min_component_fraction": float(min_component_fraction),
        "smoothing_px": float(smoothing_px),
        "simplify_px": float(simplify_px),
        "symmetry_mode": symmetry_mode,
    }
    return contours, metadata


def extract_bilateral_refined_contours_from_slice(
    slice_mask: np.ndarray,
    z: int,
    *,
    midline_x: float,
    min_area_px: int,
    min_component_fraction: float,
    smoothing_px: float,
    simplify_px: float,
    symmetry_mode: str = "average",
) -> tuple[list[RefinedContour], dict[str, Any]]:
    slice_mask = np.asarray(slice_mask, dtype=bool)
    observed: dict[str, tuple[list[np.ndarray], int]] = {
        "left": _side_components(
            slice_mask,
            side="left",
            midline_x=midline_x,
            min_area_px=min_area_px,
            min_component_fraction=min_component_fraction,
        ),
        "right": _side_components(
            slice_mask,
            side="right",
            midline_x=midline_x,
            min_area_px=min_area_px,
            min_component_fraction=min_component_fraction,
        ),
    }
    discarded = 0
    observed_components: dict[str, list[np.ndarray]] = {}
    observed_discarded: dict[str, int] = {}
    for side, (components, discarded_count) in observed.items():
        discarded += discarded_count
        if not components:
            continue
        observed_components[side] = components
        observed_discarded[side] = discarded_count
    contours: list[RefinedContour] = []
    if symmetry_mode == "average" and observed_components:
        if "left" in observed_components and "right" in observed_components:
            component_pairs = pair_side_components(
                observed_components["left"],
                observed_components["right"],
                midline_x=midline_x,
            )
        elif "left" in observed_components:
            component_pairs = [
                (component, None) for component in observed_components["left"]
            ]
        else:
            component_pairs = [
                (None, component) for component in observed_components["right"]
            ]
        for left_component, right_component in component_pairs:
            if left_component is not None and right_component is not None:
                averaged_left = average_side_components(
                    left_component,
                    right_component,
                    midline_x=midline_x,
                )
                averaged_right = mirror_mask_x(averaged_left, midline_x)
                for side, component in [
                    ("left", averaged_left),
                    ("right", averaged_right),
                ]:
                    points = contour_points_from_component(
                        component,
                        smoothing_px=smoothing_px,
                        simplify_px=simplify_px,
                    )
                    if len(points) < 3:
                        continue
                    contours.append(
                        RefinedContour(
                            z=int(z),
                            side=side,
                            status="averaged",
                            points=points,
                            discarded_components=observed_discarded.get(side, 0),
                        )
                    )
                continue
            side = "left" if left_component is not None else "right"
            component = left_component if left_component is not None else right_component
            if component is None:
                continue
            observed_points = contour_points_from_component(
                component,
                smoothing_px=smoothing_px,
                simplify_px=simplify_px,
            )
            if len(observed_points) < 3:
                continue
            contours.append(
                RefinedContour(
                    z=int(z),
                    side=side,
                    status="observed",
                    points=observed_points,
                    discarded_components=observed_discarded.get(side, 0),
                )
            )
            inferred_side = "right" if side == "left" else "left"
            contours.append(
                RefinedContour(
                    z=int(z),
                    side=inferred_side,
                    status="inferred",
                    points=mirror_contour_points(observed_points, midline_x),
                    source_side=side,
                )
            )
        metadata = {
            "inferred_count": sum(1 for contour in contours if contour.status == "inferred"),
            "discarded_components": discarded,
        }
        return contours, metadata

    observed_points: dict[str, tuple[tuple[float, float], ...]] = {}
    for side, components in observed_components.items():
        for component in components:
            points = contour_points_from_component(
                component,
                smoothing_px=smoothing_px,
                simplify_px=simplify_px,
            )
            if len(points) < 3:
                continue
            observed_points.setdefault(side, points)
            contours.append(
                RefinedContour(
                    z=int(z),
                    side=side,
                    status="observed",
                    points=points,
                    discarded_components=observed_discarded.get(side, 0),
                )
            )
    if "left" in observed_points and "right" not in observed_points:
        contours.append(
            RefinedContour(
                z=int(z),
                side="right",
                status="inferred",
                points=mirror_contour_points(observed_points["left"], midline_x),
                source_side="left",
            )
        )
    elif "right" in observed_points and "left" not in observed_points:
        contours.append(
            RefinedContour(
                z=int(z),
                side="left",
                status="inferred",
                points=mirror_contour_points(observed_points["right"], midline_x),
                source_side="right",
            )
        )
    metadata = {
        "inferred_count": sum(1 for contour in contours if contour.status == "inferred"),
        "discarded_components": discarded,
    }
    return contours, metadata


def contour_points_from_component(
    component: np.ndarray,
    *,
    smoothing_px: float,
    simplify_px: float,
) -> tuple[tuple[float, float], ...]:
    candidates = measure.find_contours(component.astype(float), 0.5)
    if not candidates:
        return ()
    boundary = max(candidates, key=len)
    ys = boundary[:, 0]
    xs = boundary[:, 1]
    if smoothing_px > 0 and len(boundary) >= 5:
        xs = ndimage.gaussian_filter1d(xs, float(smoothing_px), mode="wrap")
        ys = ndimage.gaussian_filter1d(ys, float(smoothing_px), mode="wrap")
    points_yx = np.column_stack([ys, xs])
    if simplify_px > 0 and len(points_yx) >= 5:
        points_yx = measure.approximate_polygon(points_yx, tolerance=float(simplify_px))
    points = tuple((float(x), float(y)) for y, x in points_yx)
    if len(points) >= 2 and points[0] == points[-1]:
        points = points[:-1]
    return points


def mirror_contour_points(
    points: tuple[tuple[float, float], ...],
    midline_x: float,
) -> tuple[tuple[float, float], ...]:
    return tuple((float(2.0 * midline_x - x), float(y)) for x, y in points)


def average_side_components(
    left_component: np.ndarray,
    right_component: np.ndarray,
    *,
    midline_x: float,
) -> np.ndarray:
    left = np.asarray(left_component, dtype=bool)
    right_as_left = mirror_mask_x(np.asarray(right_component, dtype=bool), midline_x)
    if not left.any():
        return right_as_left
    if not right_as_left.any():
        return left
    averaged_field = (signed_distance(left) + signed_distance(right_as_left)) / 2.0
    return averaged_field >= 0


def pair_side_components(
    left_components: list[np.ndarray],
    right_components: list[np.ndarray],
    *,
    midline_x: float,
) -> list[tuple[np.ndarray | None, np.ndarray | None]]:
    right_as_left = [
        mirror_mask_x(component, midline_x) for component in right_components
    ]
    pairs: list[tuple[np.ndarray | None, np.ndarray | None]] = []
    available_right = set(range(len(right_components)))
    left_order = sorted(
        range(len(left_components)),
        key=lambda index: int(np.count_nonzero(left_components[index])),
        reverse=True,
    )
    for left_index in left_order:
        left_component = left_components[left_index]
        if not available_right:
            pairs.append((left_component, None))
            continue
        overlaps = [
            (
                right_index,
                int(np.count_nonzero(left_component & right_as_left[right_index])),
            )
            for right_index in available_right
        ]
        best_index, best_overlap = max(overlaps, key=lambda item: item[1])
        if best_overlap <= 0:
            left_centroid = component_centroid_yx(left_component)
            best_index = min(
                available_right,
                key=lambda right_index: squared_distance_yx(
                    left_centroid,
                    component_centroid_yx(right_as_left[right_index]),
                ),
            )
        available_right.remove(best_index)
        pairs.append((left_component, right_components[best_index]))
    for right_index in sorted(available_right):
        pairs.append((None, right_components[right_index]))
    return pairs


def component_centroid_yx(component: np.ndarray) -> tuple[float, float]:
    y_indices, x_indices = np.nonzero(component)
    if len(y_indices) == 0:
        return (0.0, 0.0)
    return (float(np.mean(y_indices)), float(np.mean(x_indices)))


def squared_distance_yx(
    first: tuple[float, float],
    second: tuple[float, float],
) -> float:
    dy = first[0] - second[0]
    dx = first[1] - second[1]
    return dy * dy + dx * dx


def mirror_mask_x(mask: np.ndarray, midline_x: float) -> np.ndarray:
    mask = np.asarray(mask, dtype=bool)
    mirrored = np.zeros_like(mask, dtype=bool)
    y_indices, x_indices = np.nonzero(mask)
    mirrored_x = np.rint(2.0 * float(midline_x) - x_indices).astype(int)
    valid = (mirrored_x >= 0) & (mirrored_x < mask.shape[1])
    mirrored[y_indices[valid], mirrored_x[valid]] = True
    return mirrored


def _side_components(
    slice_mask: np.ndarray,
    *,
    side: str,
    midline_x: float,
    min_area_px: int,
    min_component_fraction: float,
) -> tuple[list[np.ndarray], int]:
    y_size, x_size = slice_mask.shape
    xs = np.arange(x_size)
    if side == "left":
        side_mask = slice_mask & (xs[None, :] < midline_x)
    elif side == "right":
        side_mask = slice_mask & (xs[None, :] >= midline_x)
    else:
        raise ValueError(f"Unknown side: {side}")
    labels, count = ndimage.label(side_mask)
    if count == 0:
        return [], 0
    sizes = np.bincount(labels.ravel())
    component_sizes = sizes[1:]
    if len(component_sizes) == 0:
        return [], 0
    largest = int(component_sizes.max())
    relative_min = int(np.ceil(largest * max(0.0, float(min_component_fraction))))
    required = max(1, int(min_area_px), relative_min)
    candidates = [
        (index + 1, int(size))
        for index, size in enumerate(component_sizes)
        if int(size) >= required
    ]
    if not candidates:
        return [], count
    candidates.sort(key=lambda item: item[1], reverse=True)
    discarded = max(0, count - len(candidates))
    components = [
        (labels == keep_label).reshape((y_size, x_size))
        for keep_label, _size in candidates
    ]
    return components, discarded
