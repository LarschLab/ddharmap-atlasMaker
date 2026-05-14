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
                channels=[ChannelInfo(index=0, gene="npy", wavelength_nm=546)],
                axes="ZCYX",
                shape=(10, 1, 20, 30),
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


def test_file_statuses():
    file_state = StackFileState(path="/tmp/sample.lsm")
    assert file_state.status == "unreviewed"

    file_state.reviewed = True
    assert file_state.status == "reviewed_no_rotation"

    file_state.rotation_degrees = -3.0
    assert file_state.status == "rotation_planned"
