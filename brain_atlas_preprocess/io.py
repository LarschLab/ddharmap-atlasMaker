from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import math
import re
import struct
import zlib

import numpy as np
from scipy import ndimage
import tifffile

from .model import ChannelInfo, StackFileState


EXPECTED_GENE_WAVELENGTH_ORDER = [546, 488, 647]
DAPI_WAVELENGTH_NM = 740
DAPI_GENE = "DAPI"
SUPPORTED_INTERPOLATION = {"nearest": 0, "linear": 1, "cubic": 3}
DEFAULT_TRANSFORM_WORKERS = 4
NRRD_SPACE_UNIT = "microns"
INFERRED_WAVELENGTHS_NM = {488, 546, 647, DAPI_WAVELENGTH_NM}


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
    channel_mapping_requires_confirmation: bool = False
    channel_mapping_messages: tuple[str, ...] = ()

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


@dataclass(frozen=True)
class ChannelMappingInference:
    channels: list[ChannelInfo]
    requires_confirmation: bool = False
    messages: tuple[str, ...] = ()


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
    for index, wavelength, gene in _filename_channel_label_segments(tokens):
        if wavelength not in EXPECTED_GENE_WAVELENGTH_ORDER:
            continue
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


def infer_channel_mapping(
    path: str | Path,
    channel_count: int,
    lsm_metadata: dict[str, Any],
) -> ChannelMappingInference:
    metadata_wavelengths = _infer_metadata_channel_wavelengths(
        channel_count,
        lsm_metadata,
    )
    if metadata_wavelengths is None:
        return ChannelMappingInference(
            channels=build_channel_mapping_suggestions(path, channel_count),
            requires_confirmation=True,
            messages=("LSM channel wavelength metadata was incomplete.",),
        )

    filename_labels = _parse_filename_channel_labels(path)
    filename_genes_by_order = [
        gene for wavelength, gene in filename_labels.items()
        if wavelength != DAPI_WAVELENGTH_NM
    ]
    used_filename_wavelengths: set[int] = set()
    used_fallback_genes = 0
    messages: list[str] = []
    channels: list[ChannelInfo] = []
    for index, wavelength in enumerate(metadata_wavelengths):
        gene = filename_labels.get(wavelength)
        if gene is not None:
            used_filename_wavelengths.add(wavelength)
        elif wavelength == DAPI_WAVELENGTH_NM:
            gene = DAPI_GENE
        elif used_fallback_genes < len(filename_genes_by_order):
            gene = filename_genes_by_order[used_fallback_genes]
            used_fallback_genes += 1
        else:
            gene = f"channel_{index + 1}"
            messages.append(
                f"Channel {index + 1} was inferred as {wavelength} nm, "
                "but no filename gene token matched it."
            )

        channels.append(
            ChannelInfo(
                index=index,
                gene=gene,
                wavelength_nm=wavelength,
            )
        )

    filename_wavelengths = {
        wavelength
        for wavelength in filename_labels
        if wavelength != DAPI_WAVELENGTH_NM
    }
    metadata_gene_wavelengths = {
        channel.wavelength_nm
        for channel in channels
        if channel.gene != DAPI_GENE
    }
    unmatched_filename_wavelengths = sorted(
        filename_wavelengths - used_filename_wavelengths
    )
    for wavelength in unmatched_filename_wavelengths:
        gene = filename_labels[wavelength]
        messages.append(
            f"Filename label {gene}_{wavelength}nm did not match any "
            "metadata-inferred channel wavelength."
        )
    for wavelength in sorted(metadata_gene_wavelengths - filename_wavelengths):
        messages.append(
            f"Metadata inferred a {wavelength} nm gene channel that was not "
            "present in the filename."
        )

    requires_confirmation = bool(messages) or len(channels) != channel_count
    try:
        channels = validate_channel_mapping(channels, channel_count)
    except StackFormatError as exc:
        fallback = build_channel_mapping_suggestions(path, channel_count)
        return ChannelMappingInference(
            channels=fallback,
            requires_confirmation=True,
            messages=(*messages, str(exc)),
        )
    return ChannelMappingInference(
        channels=channels,
        requires_confirmation=requires_confirmation,
        messages=tuple(messages),
    )


def build_channel_mapping_suggestions(
    path: str | Path, channel_count: int
) -> list[ChannelInfo]:
    try:
        parsed_pairs = parse_gene_wavelength_pairs(path)
    except StackFormatError:
        parsed_pairs = {}
    channels: list[ChannelInfo] = []
    for wavelength in EXPECTED_GENE_WAVELENGTH_ORDER:
        gene = parsed_pairs.get(wavelength)
        if gene is None or len(channels) >= channel_count:
            continue
        channels.append(
            ChannelInfo(
                index=len(channels),
                gene=gene,
                wavelength_nm=wavelength,
            )
        )
    while len(channels) < channel_count:
        index = len(channels)
        channels.append(
            ChannelInfo(
                index=index,
                gene=(
                    DAPI_GENE
                    if index == channel_count - 1
                    else f"channel_{index + 1}"
                ),
                wavelength_nm=(
                    DAPI_WAVELENGTH_NM if index == channel_count - 1 else index + 1
                ),
            )
        )
    return channels


def validate_channel_mapping(
    channels: list[ChannelInfo],
    channel_count: int,
) -> list[ChannelInfo]:
    if len(channels) != channel_count:
        raise StackFormatError(
            f"Expected {channel_count} channel labels, got {len(channels)}."
        )
    seen_indices: set[int] = set()
    seen_output_names: set[str] = set()
    validated: list[ChannelInfo] = []
    for expected_index, channel in enumerate(channels):
        if channel.index != expected_index:
            raise StackFormatError(
                f"Expected channel index {expected_index}, got {channel.index}."
            )
        if channel.index in seen_indices:
            raise StackFormatError(f"Duplicate channel index {channel.index}.")
        seen_indices.add(channel.index)
        gene = channel.gene.strip()
        if not gene:
            raise StackFormatError(f"Channel {channel.index + 1} needs a name.")
        if channel.wavelength_nm <= 0:
            raise StackFormatError(
                f"Channel {channel.index + 1} needs a positive wavelength."
            )
        output_name = f"{_safe_filename_part(gene)}_{channel.wavelength_nm}nm"
        if output_name in seen_output_names:
            raise StackFormatError(
                f"Duplicate output channel label: {gene}_{channel.wavelength_nm}nm."
            )
        seen_output_names.add(output_name)
        validated.append(
            ChannelInfo(
                index=channel.index,
                gene=gene,
                wavelength_nm=channel.wavelength_nm,
            )
        )
    return validated


def read_lsm_metadata(
    path: str | Path,
    channels: list[ChannelInfo] | None = None,
) -> StackMetadata:
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
        lsm_metadata = tiff.lsm_metadata or {}
        if channels is not None:
            channel_mapping = validate_channel_mapping(channels, channel_count)
            requires_confirmation = False
            messages: tuple[str, ...] = ()
        else:
            inference = infer_channel_mapping(source, channel_count, lsm_metadata)
            if inference.requires_confirmation:
                detail = " ".join(inference.messages)
                raise StackFormatError(
                    f"Confirm channel mapping for {source.name}."
                    + (f" {detail}" if detail else "")
                )
            channel_mapping = inference.channels
            requires_confirmation = inference.requires_confirmation
            messages = inference.messages
        return StackMetadata(
            path=str(source.expanduser().resolve()),
            axes=series.axes,
            shape=tuple(int(dim) for dim in series.shape),
            dtype=str(series.dtype),
            channels=channel_mapping,
            voxel_size_x_m=_optional_float(lsm_metadata.get("VoxelSizeX")),
            voxel_size_y_m=_optional_float(lsm_metadata.get("VoxelSizeY")),
            voxel_size_z_m=_optional_float(lsm_metadata.get("VoxelSizeZ")),
            channel_mapping_requires_confirmation=requires_confirmation,
            channel_mapping_messages=messages,
        )


def make_file_state(
    path: str | Path,
    *,
    channels: list[ChannelInfo] | None = None,
    bridge_channel_index: int | None = None,
) -> StackFileState:
    metadata = read_lsm_metadata(path, channels=channels)
    file_state = StackFileState(
        path=metadata.path,
        channels=metadata.channels,
        bridge_channel_index=bridge_channel_index,
        axes=metadata.axes,
        shape=metadata.shape,
    )
    file_state.bridge_channel_index = file_state.resolved_bridge_channel_index()
    return file_state


def load_channel_mip(path: str | Path, channel_index: int) -> np.ndarray:
    return load_channel_mips(path, [channel_index])[channel_index]


def load_channel_mips(
    path: str | Path,
    channel_indices: list[int] | None = None,
) -> dict[int, np.ndarray]:
    metadata = read_unlabeled_lsm_metadata(path)
    channel_count = int(metadata.shape[1])
    if channel_indices is None:
        requested = list(range(channel_count))
    else:
        requested = list(channel_indices)
    for channel_index in requested:
        if channel_index < 0 or channel_index >= channel_count:
            raise StackFormatError(
                f"Channel index {channel_index} is out of range for {Path(path).name}."
            )
    requested_set = set(requested)
    if not requested_set:
        return {}
    mips: dict[int, np.ndarray] = {}
    with tifffile.TiffFile(path) as tiff:
        series = tiff.series[0]
        for page in series.pages:
            plane = page.asarray()
            for channel_index in requested:
                channel_plane = plane[channel_index, :, :]
                if channel_index not in mips:
                    mips[channel_index] = channel_plane.copy()
                else:
                    np.maximum(
                        mips[channel_index],
                        channel_plane,
                        out=mips[channel_index],
                    )
    if len(mips) != len(requested_set):
        raise StackFormatError(
            f"No image planes found in {Path(path).name}."
        )
    return mips


def load_labeled_channel_mip(
    path: str | Path,
    channels: list[ChannelInfo],
    channel_index: int,
) -> np.ndarray:
    metadata = read_lsm_metadata(path, channels=channels)
    channel_count = int(metadata.shape[1])
    if channel_index < 0 or channel_index >= channel_count:
        raise StackFormatError(
            f"Channel index {channel_index} is out of range for {Path(path).name}."
        )
    return load_channel_mip(path, channel_index)


def load_dapi_mip(path: str | Path) -> np.ndarray:
    metadata = read_lsm_metadata(path)
    dapi_channel = _dapi_channel(metadata.channels)
    return load_channel_mip(path, dapi_channel.index)


def read_unlabeled_lsm_metadata(path: str | Path) -> StackMetadata:
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
        lsm_metadata = tiff.lsm_metadata or {}
        inference = infer_channel_mapping(source, channel_count, lsm_metadata)
        return StackMetadata(
            path=str(source.expanduser().resolve()),
            axes=series.axes,
            shape=tuple(int(dim) for dim in series.shape),
            dtype=str(series.dtype),
            channels=inference.channels,
            voxel_size_x_m=_optional_float(lsm_metadata.get("VoxelSizeX")),
            voxel_size_y_m=_optional_float(lsm_metadata.get("VoxelSizeY")),
            voxel_size_z_m=_optional_float(lsm_metadata.get("VoxelSizeZ")),
            channel_mapping_requires_confirmation=inference.requires_confirmation,
            channel_mapping_messages=inference.messages,
        )


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


def preview_angle_to_export_angle(angle_degrees: float) -> float:
    return -float(angle_degrees)


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
    nrrd_encoding: str = "raw",
    nrrd_compression_level: int = 9,
    transform_workers: int = DEFAULT_TRANSFORM_WORKERS,
) -> Path:
    if interpolation not in SUPPORTED_INTERPOLATION:
        raise ValueError(f"Unsupported interpolation: {interpolation}")
    if transform_workers < 1:
        raise ValueError(
            f"Transform workers must be at least 1, got {transform_workers}."
        )
    source = Path(file_state.path)
    metadata = (
        read_lsm_metadata(source, channels=file_state.channels)
        if file_state.channels
        else read_lsm_metadata(source)
    )
    bridge_index = file_state.resolved_bridge_channel_index()
    if bridge_index is None:
        bridge_index = _dapi_channel(metadata.channels).index
    bridge_channel = _channel_by_index(metadata.channels, bridge_index)
    output_dir = Path(output_root) / f"{source.stem}_preprocessed"
    output_dir.mkdir(parents=True, exist_ok=True)

    with tifffile.TiffFile(source) as tiff:
        data = tiff.series[0].asarray()

    output_files: list[dict[str, Any]] = []
    qc: dict[str, Any] | None = None
    applied_rotation_degrees = preview_angle_to_export_angle(
        file_state.rotation_degrees
    )
    transformed_channels = _transform_preprocessed_channels(
        data,
        metadata.channels,
        applied_rotation_degrees,
        file_state.crop_center_yx,
        crop_size_px,
        interpolation=interpolation,
        expand_canvas=expand_canvas,
        transform_workers=transform_workers,
    )
    for channel, cropped in transformed_channels:
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
            applied_rotation_degrees=applied_rotation_degrees,
            crop_center_yx=file_state.crop_center_yx,
            crop_size_px=crop_size_px,
            encoding=nrrd_encoding,
            compression_level=nrrd_compression_level,
        )
        output_files.append(
            {
                "channel": channel.to_dict(),
                "path": str(out_path),
                "shape": list(cropped.shape),
            }
        )
        if channel.index == bridge_channel.index:
            qc_path = output_dir / "preprocess_qc_dapi_mip.png"
            _write_stack_mip_png(qc_path, cropped)
            qc = {
                "dapi_mip_path": str(qc_path),
                "bridge_channel": bridge_channel.to_dict(),
                "rotation_degrees": file_state.rotation_degrees,
                "applied_rotation_degrees": applied_rotation_degrees,
            }

    manifest = {
        **metadata.to_manifest_dict(),
        "rotation_degrees": file_state.rotation_degrees,
        "applied_rotation_degrees": applied_rotation_degrees,
        "interpolation": interpolation,
        "canvas_mode": "expand" if expand_canvas else "keep_original_size",
        "crop_size_px": crop_size_px,
        "crop_center_yx": (
            list(file_state.crop_center_yx)
            if file_state.crop_center_yx is not None
            else None
        ),
        "bridge_channel": bridge_channel.to_dict(),
        "qc": qc,
        "output_files": output_files,
    }
    manifest_path = output_dir / "preprocess_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return output_dir


def _transform_preprocessed_channels(
    data: np.ndarray,
    channels: list[ChannelInfo],
    applied_rotation_degrees: float,
    crop_center_yx: tuple[int, int] | None,
    crop_size_px: int,
    *,
    interpolation: str,
    expand_canvas: bool,
    transform_workers: int,
) -> list[tuple[ChannelInfo, np.ndarray]]:
    if transform_workers == 1 or len(channels) <= 1:
        return [
            _transform_preprocessed_channel(
                data,
                channel,
                applied_rotation_degrees,
                crop_center_yx,
                crop_size_px,
                interpolation=interpolation,
                expand_canvas=expand_canvas,
            )
            for channel in channels
        ]

    transformed: dict[int, tuple[ChannelInfo, np.ndarray]] = {}
    max_workers = min(transform_workers, len(channels))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _transform_preprocessed_channel,
                data,
                channel,
                applied_rotation_degrees,
                crop_center_yx,
                crop_size_px,
                interpolation=interpolation,
                expand_canvas=expand_canvas,
            ): channel
            for channel in channels
        }
        for future in as_completed(futures):
            channel, cropped = future.result()
            transformed[channel.index] = (channel, cropped)
    return [transformed[channel.index] for channel in channels]


def _transform_preprocessed_channel(
    data: np.ndarray,
    channel: ChannelInfo,
    applied_rotation_degrees: float,
    crop_center_yx: tuple[int, int] | None,
    crop_size_px: int,
    *,
    interpolation: str,
    expand_canvas: bool,
) -> tuple[ChannelInfo, np.ndarray]:
    channel_stack = data[:, channel.index, :, :]
    rotated = rotate_stack_zyx(
        channel_stack,
        applied_rotation_degrees,
        interpolation=interpolation,
        expand_canvas=expand_canvas,
    )
    cropped = crop_square_zyx(rotated, crop_center_yx, crop_size_px)
    return channel, cropped


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


def _parse_filename_channel_labels(path: str | Path) -> dict[int, str]:
    stem = Path(path).stem
    tokens = stem.split("_")
    labels: dict[int, str] = {}
    for _, wavelength, gene in _filename_channel_label_segments(tokens):
        if wavelength not in INFERRED_WAVELENGTHS_NM:
            continue
        if gene:
            labels[wavelength] = gene
    return labels


def _filename_channel_label_segments(
    tokens: list[str],
) -> list[tuple[int, int, str]]:
    segments: list[tuple[int, int, str]] = []
    segment_start = 0
    for index, token in enumerate(tokens):
        match = re.fullmatch(r"(\d+)(?:nm)?", token, flags=re.IGNORECASE)
        if match is None:
            continue
        wavelength = int(match.group(1))
        if wavelength not in INFERRED_WAVELENGTHS_NM:
            continue
        gene_tokens = tokens[segment_start:index]
        while len(gene_tokens) > 1 and _is_filename_prefix_token(gene_tokens[0]):
            gene_tokens = gene_tokens[1:]
        gene = "_".join(token.strip() for token in gene_tokens if token.strip())
        segments.append((index, wavelength, gene))
        segment_start = index + 1
    return segments


def _is_filename_prefix_token(token: str) -> bool:
    cleaned = token.strip()
    return bool(
        re.fullmatch(r"\d{6,8}", cleaned)
        or re.fullmatch(r"[fF]\d+", cleaned)
        or re.fullmatch(r"[lL]\d+", cleaned)
        or cleaned.lower() == "sample"
    )


def _infer_metadata_channel_wavelengths(
    channel_count: int,
    lsm_metadata: dict[str, Any],
) -> list[int] | None:
    hints: list[dict[str, Any]] = [dict() for _ in range(channel_count)]
    channel_wavelength = lsm_metadata.get("ChannelWavelength")
    if channel_wavelength is not None:
        for index, row in enumerate(channel_wavelength):
            if index >= channel_count:
                break
            try:
                start = float(row[0]) * 1_000_000_000
                stop = float(row[1]) * 1_000_000_000
            except (TypeError, ValueError, IndexError):
                continue
            hints[index]["emission_start_nm"] = start
            hints[index]["emission_stop_nm"] = stop

    scan_information = lsm_metadata.get("ScanInformation") or {}
    for track in scan_information.get("Tracks", []):
        data_channels = track.get("DataChannels", [])
        detection_channels = track.get("DetectionChannels", [])
        illumination_channels = track.get("IlluminationChannels", [])
        illumination_nm = [
            _optional_float(channel.get("Wavelength"))
            for channel in illumination_channels
        ]
        illumination_nm = [
            value for value in illumination_nm if value is not None
        ]
        for data_index, data_channel in enumerate(data_channels):
            channel_index = data_channel.get("Acquire")
            if not isinstance(channel_index, int):
                continue
            if channel_index < 0 or channel_index >= channel_count:
                continue
            detection = (
                detection_channels[data_index]
                if data_index < len(detection_channels)
                else {}
            )
            hints[channel_index]["dye_name"] = detection.get("DyeName")
            hints[channel_index]["illumination_nm"] = illumination_nm
            start = _optional_float(detection.get("SpiWavelengthStart"))
            stop = _optional_float(detection.get("SpiWavelengthStop"))
            if start is not None:
                hints[channel_index]["emission_start_nm"] = start
            if stop is not None:
                hints[channel_index]["emission_stop_nm"] = stop

    wavelengths: list[int] = []
    for hint in hints:
        wavelength = _infer_channel_wavelength_from_hint(hint)
        if wavelength is None:
            return None
        wavelengths.append(wavelength)
    if len(set(wavelengths)) != len(wavelengths):
        return None
    return wavelengths


def _infer_channel_wavelength_from_hint(hint: dict[str, Any]) -> int | None:
    dye_name = str(hint.get("dye_name") or "").lower()
    if "dapi" in dye_name:
        return DAPI_WAVELENGTH_NM
    if "egfp" in dye_name or "gfp" in dye_name or "488" in dye_name:
        return 488
    if "546" in dye_name:
        return 546
    if "647" in dye_name:
        return 647

    illumination_nm = [
        int(round(value))
        for value in hint.get("illumination_nm") or []
    ]
    if DAPI_WAVELENGTH_NM in illumination_nm:
        return DAPI_WAVELENGTH_NM
    if len(illumination_nm) == 1:
        wavelength = illumination_nm[0]
        if wavelength == 633:
            return 647
        if wavelength in {488, 546, 647}:
            return wavelength

    start = _optional_float(hint.get("emission_start_nm"))
    stop = _optional_float(hint.get("emission_stop_nm"))
    if start is None or stop is None:
        return None
    if 646 <= start <= 650:
        return 647
    if 492 <= start <= 500 and 540 <= stop <= 580:
        return 488
    return None


def _dapi_channel(channels: list[ChannelInfo]) -> ChannelInfo:
    for channel in channels:
        if channel.gene == DAPI_GENE and channel.wavelength_nm == DAPI_WAVELENGTH_NM:
            return channel
    raise StackFormatError("DAPI channel was not found in channel mapping.")


def _channel_by_index(channels: list[ChannelInfo], index: int) -> ChannelInfo:
    for channel in channels:
        if channel.index == index:
            return channel
    raise StackFormatError(f"Bridge channel index {index} was not found.")


def _preserve_dtype(array: np.ndarray, dtype: np.dtype[Any]) -> np.ndarray:
    target_dtype = np.dtype(dtype)
    if array.dtype == target_dtype:
        return array
    if np.issubdtype(target_dtype, np.integer):
        info = np.iinfo(target_dtype)
        array = np.clip(np.rint(array), info.min, info.max)
    return array.astype(target_dtype, copy=False)


def _write_stack_mip_png(path: Path, stack: np.ndarray) -> None:
    mip = stack.max(axis=0)
    _write_grayscale_png(path, _normalize_to_uint8(mip))


def _normalize_to_uint8(image: np.ndarray) -> np.ndarray:
    finite = np.nan_to_num(np.asarray(image).astype(np.float32, copy=False))
    if finite.size == 0:
        return np.zeros(finite.shape, dtype=np.uint8)
    low, high = np.percentile(finite, [1, 99.5])
    if high <= low:
        high = float(finite.max())
        low = float(finite.min())
    if high <= low:
        return np.zeros(finite.shape, dtype=np.uint8)
    normalized = np.clip((finite - low) / (high - low), 0, 1)
    return (normalized * 255).astype(np.uint8)


def _write_grayscale_png(path: Path, image: np.ndarray) -> None:
    if image.ndim != 2:
        raise ValueError(f"Expected 2-D image, got shape {image.shape}.")
    contiguous = np.ascontiguousarray(image, dtype=np.uint8)
    height, width = contiguous.shape
    raw_rows = b"".join(b"\x00" + row.tobytes() for row in contiguous)
    payload = [
        b"\x89PNG\r\n\x1a\n",
        _png_chunk(
            b"IHDR",
            struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0),
        ),
        _png_chunk(b"IDAT", zlib.compress(raw_rows)),
        _png_chunk(b"IEND", b""),
    ]
    path.write_bytes(b"".join(payload))


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(kind)
    checksum = zlib.crc32(data, checksum)
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", checksum & 0xFFFFFFFF)
    )


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
    applied_rotation_degrees: float,
    crop_center_yx: tuple[int, int] | None,
    crop_size_px: int,
    encoding: str = "raw",
    compression_level: int = 9,
) -> None:
    import nrrd

    header: dict[str, Any] = {
        "dimension": 3,
        "kinds": ["domain", "domain", "domain"],
        "encoding": encoding,
        "source_path": metadata.path,
        "source_name": Path(metadata.path).name,
        "source_axes": metadata.axes,
        "array_axes": "ZYX",
        "source_shape": json.dumps(list(metadata.shape)),
        "source_dtype": metadata.dtype,
        "channel_index": channel.index,
        "channel_gene": channel.gene,
        "channel_wavelength_nm": channel.wavelength_nm,
        "rotation_degrees": float(rotation_degrees),
        "applied_rotation_degrees": float(applied_rotation_degrees),
        "crop_size_px": int(crop_size_px),
        "crop_center_yx": json.dumps(list(crop_center_yx) if crop_center_yx else None),
        "labels": ["x", "y", "z"],
    }
    space_directions_microns = _nrrd_space_directions_microns(metadata)
    if space_directions_microns is not None:
        header["space dimension"] = 3
        header["space directions"] = space_directions_microns
        header["space units"] = [NRRD_SPACE_UNIT, NRRD_SPACE_UNIT, NRRD_SPACE_UNIT]

    # The in-memory stack is NumPy C-order ZYX. pynrrd defaults to Fortran
    # axis order, which writes a header external tools can interpret as XYZ.
    nrrd.write(
        str(path),
        stack,
        header=header,
        index_order="C",
        compression_level=compression_level,
    )


def _nrrd_space_directions_microns(
    metadata: StackMetadata,
) -> list[list[float]] | None:
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
    return [
        [x_um, 0.0, 0.0],
        [0.0, y_um, 0.0],
        [0.0, 0.0, z_um],
    ]


def _safe_filename_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.()+-]+", "_", value.strip())
    return cleaned or "channel"
