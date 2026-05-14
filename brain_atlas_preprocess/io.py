from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import math
import re

import numpy as np
from scipy import ndimage
import tifffile

from .model import ChannelInfo, StackFileState


EXPECTED_GENE_WAVELENGTH_ORDER = [546, 488, 647]
DAPI_WAVELENGTH_NM = 740
DAPI_GENE = "DAPI"
SUPPORTED_INTERPOLATION = {"nearest": 0, "linear": 1, "cubic": 3}


class StackFormatError(ValueError):
    """Raised when an input stack does not match the expected LSM contract."""


@dataclass(frozen=True)
class StackMetadata:
    path: str
    axes: str
    shape: tuple[int, ...]
    dtype: str
    channels: list[ChannelInfo]
    voxel_size_x_m: float | None = None
    voxel_size_y_m: float | None = None
    voxel_size_z_m: float | None = None

    def to_manifest_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.path,
            "axes": self.axes,
            "shape": list(self.shape),
            "dtype": self.dtype,
            "voxel_size_m": {
                "x": self.voxel_size_x_m,
                "y": self.voxel_size_y_m,
                "z": self.voxel_size_z_m,
            },
            "channels": [channel.to_dict() for channel in self.channels],
        }


def parse_gene_wavelength_pairs(path: str | Path) -> dict[int, str]:
    """Parse gene/wavelength pairs from a stack filename.

    The sample filenames encode pairs as `<gene>_<wavelength>`, for example
    `arxa_488_shha_546_mc4r_647`. Prefix tokens such as date/fish id and
    suffix tokens such as `Stitch` are ignored because only supported
    wavelengths are consumed.
    """

    stem = Path(path).stem
    tokens = stem.split("_")
    pairs: dict[int, str] = {}
    for index, token in enumerate(tokens):
        if not token.isdigit():
            continue
        wavelength = int(token)
        if wavelength not in EXPECTED_GENE_WAVELENGTH_ORDER:
            continue
        if index == 0:
            raise StackFormatError(f"Missing gene name before wavelength {wavelength}.")
        gene = tokens[index - 1].strip()
        if not gene:
            raise StackFormatError(f"Missing gene name before wavelength {wavelength}.")
        pairs[wavelength] = gene
    if not pairs:
        raise StackFormatError(f"No gene/wavelength pairs found in {Path(path).name}.")
    return pairs


def build_channel_mapping(path: str | Path, channel_count: int) -> list[ChannelInfo]:
    parsed_pairs = parse_gene_wavelength_pairs(path)
    channels: list[ChannelInfo] = []
    for wavelength in EXPECTED_GENE_WAVELENGTH_ORDER:
        gene = parsed_pairs.get(wavelength)
        if gene is not None:
            channels.append(
                ChannelInfo(
                    index=len(channels),
                    gene=gene,
                    wavelength_nm=wavelength,
                )
            )
    channels.append(
        ChannelInfo(
            index=len(channels),
            gene=DAPI_GENE,
            wavelength_nm=DAPI_WAVELENGTH_NM,
        )
    )
    if len(channels) != channel_count:
        labels = ", ".join(channel.label for channel in channels)
        raise StackFormatError(
            f"Parsed {len(channels)} channels from filename but LSM has "
            f"{channel_count} channels: {Path(path).name}. Parsed: {labels}"
        )
    return channels


def read_lsm_metadata(path: str | Path) -> StackMetadata:
    source = Path(path)
    with tifffile.TiffFile(source) as tiff:
        if not tiff.is_lsm:
            raise StackFormatError(f"Expected a Zeiss LSM/TIFF file: {source}")
        series = tiff.series[0]
        if series.axes != "ZCYX":
            raise StackFormatError(
                f"Expected primary LSM axes ZCYX, got {series.axes}: {source.name}"
            )
        if len(series.shape) != 4:
            raise StackFormatError(
                f"Expected four-dimensional ZCYX data, got {series.shape}: "
                f"{source.name}"
            )
        channel_count = int(series.shape[1])
        channels = build_channel_mapping(source, channel_count)
        lsm_metadata = tiff.lsm_metadata or {}
        return StackMetadata(
            path=str(source.expanduser().resolve()),
            axes=series.axes,
            shape=tuple(int(dim) for dim in series.shape),
            dtype=str(series.dtype),
            channels=channels,
            voxel_size_x_m=_optional_float(lsm_metadata.get("VoxelSizeX")),
            voxel_size_y_m=_optional_float(lsm_metadata.get("VoxelSizeY")),
            voxel_size_z_m=_optional_float(lsm_metadata.get("VoxelSizeZ")),
        )


def make_file_state(path: str | Path) -> StackFileState:
    metadata = read_lsm_metadata(path)
    return StackFileState(
        path=metadata.path,
        channels=metadata.channels,
        axes=metadata.axes,
        shape=metadata.shape,
    )


def load_dapi_mip(path: str | Path) -> np.ndarray:
    metadata = read_lsm_metadata(path)
    dapi_channel = _dapi_channel(metadata.channels)
    with tifffile.TiffFile(path) as tiff:
        series = tiff.series[0]
        mip: np.ndarray | None = None
        for page in series.pages:
            plane = page.asarray()[dapi_channel.index, :, :]
            if mip is None:
                mip = plane.copy()
            else:
                np.maximum(mip, plane, out=mip)
    if mip is None:
        raise StackFormatError(f"No image planes found in {Path(path).name}.")
    return mip


def rotate_stack_zyx(
    stack: np.ndarray,
    angle_degrees: float,
    *,
    interpolation: str = "linear",
    expand_canvas: bool = True,
) -> np.ndarray:
    if stack.ndim != 3:
        raise ValueError(f"Expected ZYX stack, got shape {stack.shape}.")
    order = SUPPORTED_INTERPOLATION[interpolation]
    if math.isclose(angle_degrees, 0.0, abs_tol=1e-9):
        return stack.copy()
    rotated = ndimage.rotate(
        stack,
        angle=angle_degrees,
        axes=(-2, -1),
        reshape=expand_canvas,
        order=order,
        mode="constant",
        cval=0,
        prefilter=order > 1,
    )
    return _preserve_dtype(rotated, stack.dtype)


def crop_square_zyx(
    stack: np.ndarray,
    center_yx: tuple[int, int] | None,
    size_px: int,
) -> np.ndarray:
    if stack.ndim != 3:
        raise ValueError(f"Expected ZYX stack, got shape {stack.shape}.")
    if size_px < 1:
        raise ValueError(f"Crop size must be at least 1 pixel, got {size_px}.")

    if center_yx is None:
        center_y = stack.shape[1] // 2
        center_x = stack.shape[2] // 2
    else:
        center_y, center_x = center_yx

    start_y = int(center_y) - size_px // 2
    start_x = int(center_x) - size_px // 2
    end_y = start_y + size_px
    end_x = start_x + size_px

    source_start_y = max(0, start_y)
    source_start_x = max(0, start_x)
    source_end_y = min(stack.shape[1], end_y)
    source_end_x = min(stack.shape[2], end_x)

    cropped = np.zeros((stack.shape[0], size_px, size_px), dtype=stack.dtype)
    if source_start_y >= source_end_y or source_start_x >= source_end_x:
        return cropped

    target_start_y = source_start_y - start_y
    target_start_x = source_start_x - start_x
    target_end_y = target_start_y + (source_end_y - source_start_y)
    target_end_x = target_start_x + (source_end_x - source_start_x)
    cropped[:, target_start_y:target_end_y, target_start_x:target_end_x] = stack[
        :, source_start_y:source_end_y, source_start_x:source_end_x
    ]
    return cropped


def export_preprocessed_channels(
    file_state: StackFileState,
    output_root: str | Path,
    *,
    interpolation: str = "linear",
    expand_canvas: bool = True,
    crop_size_px: int = 750,
) -> Path:
    if interpolation not in SUPPORTED_INTERPOLATION:
        raise ValueError(f"Unsupported interpolation: {interpolation}")
    source = Path(file_state.path)
    metadata = read_lsm_metadata(source)
    output_dir = Path(output_root) / f"{source.stem}_preprocessed"
    output_dir.mkdir(parents=True, exist_ok=True)

    with tifffile.TiffFile(source) as tiff:
        data = tiff.series[0].asarray()

    output_files: list[dict[str, Any]] = []
    for channel in metadata.channels:
        channel_stack = data[:, channel.index, :, :]
        rotated = rotate_stack_zyx(
            channel_stack,
            file_state.rotation_degrees,
            interpolation=interpolation,
            expand_canvas=expand_canvas,
        )
        cropped = crop_square_zyx(rotated, file_state.crop_center_yx, crop_size_px)
        out_name = (
            f"{source.stem}_{_safe_filename_part(channel.gene)}_"
            f"{channel.wavelength_nm}nm_preprocessed.nrrd"
        )
        out_path = output_dir / out_name
        _write_stack_nrrd(
            out_path,
            cropped,
            metadata,
            channel=channel,
            rotation_degrees=file_state.rotation_degrees,
            crop_center_yx=file_state.crop_center_yx,
            crop_size_px=crop_size_px,
        )
        output_files.append(
            {
                "channel": channel.to_dict(),
                "path": str(out_path),
                "shape": list(cropped.shape),
            }
        )

    manifest = {
        **metadata.to_manifest_dict(),
        "rotation_degrees": file_state.rotation_degrees,
        "interpolation": interpolation,
        "canvas_mode": "expand" if expand_canvas else "keep_original_size",
        "crop_size_px": crop_size_px,
        "crop_center_yx": (
            list(file_state.crop_center_yx)
            if file_state.crop_center_yx is not None
            else None
        ),
        "output_files": output_files,
    }
    manifest_path = output_dir / "preprocess_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return output_dir


def export_rotated_channels(
    file_state: StackFileState,
    output_root: str | Path,
    *,
    interpolation: str = "linear",
    expand_canvas: bool = True,
) -> Path:
    return export_preprocessed_channels(
        file_state,
        output_root,
        interpolation=interpolation,
        expand_canvas=expand_canvas,
    )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dapi_channel(channels: list[ChannelInfo]) -> ChannelInfo:
    for channel in channels:
        if channel.gene == DAPI_GENE and channel.wavelength_nm == DAPI_WAVELENGTH_NM:
            return channel
    raise StackFormatError("DAPI channel was not found in channel mapping.")


def _preserve_dtype(array: np.ndarray, dtype: np.dtype[Any]) -> np.ndarray:
    target_dtype = np.dtype(dtype)
    if array.dtype == target_dtype:
        return array
    if np.issubdtype(target_dtype, np.integer):
        info = np.iinfo(target_dtype)
        array = np.clip(np.rint(array), info.min, info.max)
    return array.astype(target_dtype, copy=False)


def _write_stack_tiff(path: Path, stack: np.ndarray, metadata: StackMetadata) -> None:
    imagej_metadata: dict[str, Any] = {"axes": "ZYX"}
    if metadata.voxel_size_z_m:
        imagej_metadata["spacing"] = metadata.voxel_size_z_m * 1_000_000
        imagej_metadata["unit"] = "um"

    kwargs: dict[str, Any] = {
        "imagej": True,
        "metadata": imagej_metadata,
        "photometric": "minisblack",
    }
    if metadata.voxel_size_x_m and metadata.voxel_size_y_m:
        x_um = metadata.voxel_size_x_m * 1_000_000
        y_um = metadata.voxel_size_y_m * 1_000_000
        if x_um > 0 and y_um > 0:
            kwargs["resolution"] = (1 / x_um, 1 / y_um)
    tifffile.imwrite(path, stack, **kwargs)


def _write_stack_nrrd(
    path: Path,
    stack: np.ndarray,
    metadata: StackMetadata,
    *,
    channel: ChannelInfo,
    rotation_degrees: float,
    crop_center_yx: tuple[int, int] | None,
    crop_size_px: int,
) -> None:
    import nrrd

    header: dict[str, Any] = {
        "dimension": 3,
        "kinds": ["domain", "domain", "domain"],
        "encoding": "gzip",
        "source_path": metadata.path,
        "source_name": Path(metadata.path).name,
        "source_axes": metadata.axes,
        "source_shape": json.dumps(list(metadata.shape)),
        "source_dtype": metadata.dtype,
        "channel_index": channel.index,
        "channel_gene": channel.gene,
        "channel_wavelength_nm": channel.wavelength_nm,
        "rotation_degrees": float(rotation_degrees),
        "crop_size_px": int(crop_size_px),
        "crop_center_yx": json.dumps(list(crop_center_yx) if crop_center_yx else None),
    }
    spacings_um = _voxel_spacings_um(metadata)
    if spacings_um is not None:
        header["spacings"] = spacings_um
        header["space units"] = ["um", "um", "um"]

    nrrd.write(str(path), stack, header=header)


def _voxel_spacings_um(metadata: StackMetadata) -> list[float] | None:
    if not (
        metadata.voxel_size_z_m
        and metadata.voxel_size_y_m
        and metadata.voxel_size_x_m
    ):
        return None
    z_um = metadata.voxel_size_z_m * 1_000_000
    y_um = metadata.voxel_size_y_m * 1_000_000
    x_um = metadata.voxel_size_x_m * 1_000_000
    if z_um <= 0 or y_um <= 0 or x_um <= 0:
        return None
    return [z_um, y_um, x_um]


def _safe_filename_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.()+-]+", "_", value.strip())
    return cleaned or "channel"
