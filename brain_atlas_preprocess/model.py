from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json


PROJECT_FILENAME = "brain_atlas_preprocess_project.json"
ANGLE_EPSILON = 1e-3


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


@dataclass
class StackFileState:
    path: str
    rotation_degrees: float = 0.0
    reviewed: bool = False
    channels: list[ChannelInfo] = field(default_factory=list)
    axes: str | None = None
    shape: tuple[int, ...] | None = None

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "rotation_degrees": self.rotation_degrees,
            "reviewed": self.reviewed,
            "channels": [channel.to_dict() for channel in self.channels],
            "axes": self.axes,
            "shape": list(self.shape) if self.shape is not None else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StackFileState":
        shape = data.get("shape")
        return cls(
            path=str(data["path"]),
            rotation_degrees=float(data.get("rotation_degrees", 0.0)),
            reviewed=bool(data.get("reviewed", False)),
            channels=[
                ChannelInfo.from_dict(channel) for channel in data.get("channels", [])
            ],
            axes=data.get("axes"),
            shape=tuple(shape) if shape is not None else None,
        )


@dataclass
class ProjectState:
    output_root: str | None = None
    files: list[StackFileState] = field(default_factory=list)
    interpolation: str = "linear"
    canvas_mode: str = "expand"

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "output_root": self.output_root,
            "interpolation": self.interpolation,
            "canvas_mode": self.canvas_mode,
            "files": [file_state.to_dict() for file_state in self.files],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectState":
        return cls(
            output_root=data.get("output_root"),
            interpolation=str(data.get("interpolation", "linear")),
            canvas_mode=str(data.get("canvas_mode", "expand")),
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
