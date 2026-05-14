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


def export_rotated_channels(
    file_state: StackFileState,
    output_root: str | Path,
    *,
    interpolation: str = "linear",
    expand_canvas: bool = True,
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
        out_name = (
            f"{source.stem}_{_safe_filename_part(channel.gene)}_"
            f"{channel.wavelength_nm}nm_rotated.tif"
        )
        out_path = output_dir / out_name
        _write_stack_tiff(out_path, rotated, metadata)
        output_files.append(
            {
                "channel": channel.to_dict(),
                "path": str(out_path),
                "shape": list(rotated.shape),
            }
        )

    manifest = {
        **metadata.to_manifest_dict(),
        "rotation_degrees": file_state.rotation_degrees,
        "interpolation": interpolation,
        "canvas_mode": "expand" if expand_canvas else "keep_original_size",
        "output_files": output_files,
    }
    manifest_path = output_dir / "preprocess_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return output_dir


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


def _safe_filename_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.()+-]+", "_", value.strip())
    return cleaned or "channel"
