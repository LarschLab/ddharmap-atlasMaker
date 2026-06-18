from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json


PROJECT_FILENAME = "brain_atlas_preprocess_project.json"
ANGLE_EPSILON = 1e-3
DEFAULT_CROP_SIZE_PX = 750
SAME_FISH_CONFOCAL_PROFILE = "same_fish_confocal"
SAME_FISH_CONFOCAL_CROP_SIZE_PX = 1500


@dataclass(frozen=True)
class ChannelInfo:
    index: int
    gene: str
    wavelength_nm: int

    @property
    def label(self) -> str:
        return f"{self.gene}_{self.wavelength_nm}nm"

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "gene": self.gene,
            "wavelength_nm": self.wavelength_nm,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChannelInfo":
        return cls(
            index=int(data["index"]),
            gene=str(data["gene"]),
            wavelength_nm=int(data["wavelength_nm"]),
        )


@dataclass(frozen=True)
class SameFishConfocalProfile:
    fish_id: str
    round_role: str
    round_number: int | None = None

    def __post_init__(self) -> None:
        fish_id = self.fish_id.strip()
        round_role = self.round_role.strip().lower()
        if not fish_id:
            raise ValueError("Same-fish confocal profile requires a fish ID.")
        if round_role not in {"rbest", "rn"}:
            raise ValueError("Same-fish confocal round role must be rbest or rn.")
        if round_role == "rn" and self.round_number is None:
            raise ValueError("Same-fish confocal rn exports require a round number.")
        if self.round_number is not None and self.round_number < 1:
            raise ValueError("Same-fish confocal round number must be positive.")
        object.__setattr__(self, "fish_id", fish_id)
        object.__setattr__(self, "round_role", round_role)

    @property
    def round_label(self) -> str:
        if self.round_role == "rbest":
            return "rbest"
        if self.round_number is None:
            raise ValueError("Same-fish confocal rn exports require a round number.")
        return f"r{self.round_number}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": SAME_FISH_CONFOCAL_PROFILE,
            "fish_id": self.fish_id,
            "round_role": self.round_role,
            "round_number": self.round_number,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SameFishConfocalProfile":
        profile = data.get("profile", SAME_FISH_CONFOCAL_PROFILE)
        if profile != SAME_FISH_CONFOCAL_PROFILE:
            raise ValueError(f"Unsupported export profile: {profile}")
        round_number = data.get("round_number")
        return cls(
            fish_id=str(data["fish_id"]),
            round_role=str(data["round_role"]),
            round_number=int(round_number) if round_number is not None else None,
        )


@dataclass
class StackFileState:
    path: str
    rotation_degrees: float = 0.0
    reviewed: bool = False
    crop_center_yx: tuple[int, int] | None = None
    channels: list[ChannelInfo] = field(default_factory=list)
    bridge_channel_index: int | None = None
    axes: str | None = None
    shape: tuple[int, ...] | None = None
    output_root: str | None = None
    same_fish_confocal: SameFishConfocalProfile | None = None

    @property
    def name(self) -> str:
        return Path(self.path).name

    @property
    def status(self) -> str:
        if not self.reviewed:
            return "unreviewed"
        if abs(self.rotation_degrees) > ANGLE_EPSILON:
            return "rotation_planned"
        return "reviewed_no_rotation"

    def resolved_bridge_channel_index(self) -> int | None:
        if not self.channels:
            return None
        channel_indices = {channel.index for channel in self.channels}
        if self.bridge_channel_index in channel_indices:
            return self.bridge_channel_index
        for channel in self.channels:
            if channel.gene == "DAPI" and channel.wavelength_nm == 740:
                return channel.index
        return self.channels[-1].index

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "rotation_degrees": self.rotation_degrees,
            "reviewed": self.reviewed,
            "crop_center_yx": (
                list(self.crop_center_yx) if self.crop_center_yx is not None else None
            ),
            "channels": [channel.to_dict() for channel in self.channels],
            "bridge_channel_index": self.resolved_bridge_channel_index(),
            "axes": self.axes,
            "shape": list(self.shape) if self.shape is not None else None,
            "output_root": self.output_root,
            "same_fish_confocal": (
                self.same_fish_confocal.to_dict()
                if self.same_fish_confocal is not None
                else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StackFileState":
        shape = data.get("shape")
        crop_center = data.get("crop_center_yx")
        same_fish_confocal = data.get("same_fish_confocal")
        file_state = cls(
            path=str(data["path"]),
            rotation_degrees=float(data.get("rotation_degrees", 0.0)),
            reviewed=bool(data.get("reviewed", False)),
            crop_center_yx=(
                (int(crop_center[0]), int(crop_center[1]))
                if crop_center is not None
                else None
            ),
            channels=[
                ChannelInfo.from_dict(channel) for channel in data.get("channels", [])
            ],
            bridge_channel_index=(
                int(data["bridge_channel_index"])
                if data.get("bridge_channel_index") is not None
                else None
            ),
            axes=data.get("axes"),
            shape=tuple(shape) if shape is not None else None,
            output_root=data.get("output_root"),
            same_fish_confocal=(
                SameFishConfocalProfile.from_dict(same_fish_confocal)
                if same_fish_confocal is not None
                else None
            ),
        )
        file_state.bridge_channel_index = file_state.resolved_bridge_channel_index()
        return file_state


@dataclass
class ProjectState:
    output_root: str | None = None
    files: list[StackFileState] = field(default_factory=list)
    interpolation: str = "linear"
    canvas_mode: str = "expand"
    crop_size_px: int = DEFAULT_CROP_SIZE_PX
    same_fish_confocal: SameFishConfocalProfile | None = None

    def project_path(self) -> Path | None:
        if not self.output_root:
            return None
        return Path(self.output_root) / PROJECT_FILENAME

    def add_or_update_file(self, file_state: StackFileState) -> None:
        resolved = str(Path(file_state.path).expanduser().resolve())
        file_state.path = resolved
        for index, existing in enumerate(self.files):
            if str(Path(existing.path).expanduser().resolve()) == resolved:
                self.files[index] = file_state
                return
        self.files.append(file_state)

    def get_file(self, path: str) -> StackFileState | None:
        resolved = Path(path).expanduser().resolve()
        for file_state in self.files:
            if Path(file_state.path).expanduser().resolve() == resolved:
                return file_state
        return None

    def remove_files(self, paths: list[str]) -> list[StackFileState]:
        resolved_paths = {
            Path(path).expanduser().resolve()
            for path in paths
        }
        removed: list[StackFileState] = []
        remaining: list[StackFileState] = []
        for file_state in self.files:
            if Path(file_state.path).expanduser().resolve() in resolved_paths:
                removed.append(file_state)
            else:
                remaining.append(file_state)
        self.files = remaining
        return removed

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "output_root": self.output_root,
            "interpolation": self.interpolation,
            "canvas_mode": self.canvas_mode,
            "crop_size_px": self.crop_size_px,
            "same_fish_confocal": (
                self.same_fish_confocal.to_dict()
                if self.same_fish_confocal is not None
                else None
            ),
            "files": [file_state.to_dict() for file_state in self.files],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectState":
        same_fish_confocal = data.get("same_fish_confocal")
        return cls(
            output_root=data.get("output_root"),
            interpolation=str(data.get("interpolation", "linear")),
            canvas_mode=str(data.get("canvas_mode", "expand")),
            crop_size_px=int(data.get("crop_size_px", DEFAULT_CROP_SIZE_PX)),
            same_fish_confocal=(
                SameFishConfocalProfile.from_dict(same_fish_confocal)
                if same_fish_confocal is not None
                else None
            ),
            files=[
                StackFileState.from_dict(file_state)
                for file_state in data.get("files", [])
            ],
        )

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path is not None else self.project_path()
        if target is None:
            raise ValueError("Select an output root before saving project state.")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return target

    @classmethod
    def load(cls, path: str | Path) -> "ProjectState":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)
