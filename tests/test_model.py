from pathlib import Path

from brain_atlas_preprocess.model import (
    DEFAULT_CROP_SIZE_PX,
    ChannelInfo,
    ProjectState,
    StackFileState,
)


def test_project_state_round_trip(tmp_path):
    project = ProjectState(
        output_root=str(tmp_path),
        crop_size_px=512,
        files=[
            StackFileState(
                path="/tmp/sample.lsm",
                rotation_degrees=12.5,
                reviewed=True,
                crop_center_yx=(123, 456),
                channels=[
                    ChannelInfo(index=0, gene="npy", wavelength_nm=546),
                    ChannelInfo(index=1, gene="bridge", wavelength_nm=740),
                ],
                bridge_channel_index=1,
                axes="ZCYX",
                shape=(10, 2, 20, 30),
            )
        ],
    )

    saved = project.save()
    loaded = ProjectState.load(saved)

    assert loaded.output_root == str(tmp_path)
    assert loaded.crop_size_px == 512
    assert loaded.files[0].path == "/tmp/sample.lsm"
    assert loaded.files[0].rotation_degrees == 12.5
    assert loaded.files[0].crop_center_yx == (123, 456)
    assert loaded.files[0].bridge_channel_index == 1
    assert loaded.files[0].status == "rotation_planned"
    assert loaded.files[0].channels[0].label == "npy_546nm"


def test_project_state_loads_legacy_crop_defaults():
    project = ProjectState.from_dict(
        {
            "output_root": "/tmp/out",
            "files": [{"path": "/tmp/sample.lsm"}],
        }
    )

    assert project.crop_size_px == DEFAULT_CROP_SIZE_PX
    assert project.files[0].crop_center_yx is None


def test_project_state_loads_legacy_bridge_channel_from_dapi():
    project = ProjectState.from_dict(
        {
            "output_root": "/tmp/out",
            "files": [
                {
                    "path": "/tmp/sample.lsm",
                    "channels": [
                        {"index": 0, "gene": "npy", "wavelength_nm": 546},
                        {"index": 1, "gene": "DAPI", "wavelength_nm": 740},
                    ],
                }
            ],
        }
    )

    assert project.files[0].bridge_channel_index == 1


def test_project_state_loads_legacy_bridge_channel_from_last_channel():
    project = ProjectState.from_dict(
        {
            "output_root": "/tmp/out",
            "files": [
                {
                    "path": "/tmp/sample.lsm",
                    "channels": [
                        {"index": 0, "gene": "npy", "wavelength_nm": 546},
                        {"index": 1, "gene": "bridge", "wavelength_nm": 555},
                    ],
                }
            ],
        }
    )

    assert project.files[0].bridge_channel_index == 1


def test_file_statuses():
    file_state = StackFileState(path="/tmp/sample.lsm")
    assert file_state.status == "unreviewed"

    file_state.reviewed = True
    assert file_state.status == "reviewed_no_rotation"

    file_state.rotation_degrees = -3.0
    assert file_state.status == "rotation_planned"


def test_project_state_removes_files_by_resolved_path(tmp_path):
    keep = tmp_path / "keep.lsm"
    remove_a = tmp_path / "remove_a.lsm"
    remove_b = tmp_path / "remove_b.lsm"
    for path in [keep, remove_a, remove_b]:
        path.write_text("", encoding="utf-8")
    project = ProjectState(
        files=[
            StackFileState(path=str(remove_a)),
            StackFileState(path=str(keep)),
            StackFileState(path=str(remove_b)),
        ],
    )

    removed = project.remove_files([
        str(remove_a),
        str(tmp_path / "." / "remove_b.lsm"),
        str(tmp_path / "missing.lsm"),
    ])

    assert [Path(file_state.path).name for file_state in removed] == [
        "remove_a.lsm",
        "remove_b.lsm",
    ]
    assert [Path(file_state.path).name for file_state in project.files] == [
        "keep.lsm",
    ]
