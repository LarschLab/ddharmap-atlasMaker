from pathlib import Path

from brain_atlas_preprocess.app import PreprocessWorker, _parse_args
from brain_atlas_preprocess.model import SameFishConfocalProfile, StackFileState


def test_preprocess_worker_uses_file_specific_output_roots_and_profiles(monkeypatch):
    calls = []

    def fake_export(file_state, output_root, **kwargs):
        calls.append((file_state.path, output_root, kwargs["same_fish_confocal"]))
        return Path(output_root) / "rbest"

    monkeypatch.setattr(
        "brain_atlas_preprocess.app.export_preprocessed_channels",
        fake_export,
    )
    files = [
        StackFileState(
            path="/tmp/L765_f02.lsm",
            output_root="/tmp/L765_f02/02_reg/00_preprocessing",
            same_fish_confocal=SameFishConfocalProfile(
                fish_id="L765_f02",
                round_role="rbest",
            ),
        ),
        StackFileState(
            path="/tmp/L765_f03.lsm",
            output_root="/tmp/L765_f03/02_reg/00_preprocessing",
            same_fish_confocal=SameFishConfocalProfile(
                fish_id="L765_f03",
                round_role="rbest",
            ),
        ),
    ]
    worker = PreprocessWorker(files, "/tmp/batch", 1500)

    worker.run()

    assert calls == [
        (
            "/tmp/L765_f02.lsm",
            "/tmp/L765_f02/02_reg/00_preprocessing",
            SameFishConfocalProfile(fish_id="L765_f02", round_role="rbest"),
        ),
        (
            "/tmp/L765_f03.lsm",
            "/tmp/L765_f03/02_reg/00_preprocessing",
            SameFishConfocalProfile(fish_id="L765_f03", round_role="rbest"),
        ),
    ]


def test_parse_args_rejects_project_with_positional_stacks():
    try:
        _parse_args(["--project", "/tmp/project.json", "/tmp/sample.lsm"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("Expected parser to reject mixed project/input launch")
