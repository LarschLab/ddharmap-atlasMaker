from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest


def _load_repair_module():
    script_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "repair_nrrd_space_units.py"
    )
    spec = importlib.util.spec_from_file_location("repair_nrrd_space_units", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repair_nrrd_space_units_changes_only_unit_token(tmp_path):
    nrrd = pytest.importorskip("nrrd")
    repair = _load_repair_module()
    data = np.arange(2 * 3 * 4, dtype=np.uint16).reshape(2, 3, 4)
    path = tmp_path / "sample.nrrd"
    nrrd.write(
        str(path),
        data,
        header={
            "dimension": 3,
            "space dimension": 3,
            "space directions": [
                [1.0, 0.0, 0.0],
                [0.0, 2.0, 0.0],
                [0.0, 0.0, 3.0],
            ],
            "space units": ["um", "um", "um"],
            "encoding": "raw",
        },
        index_order="C",
    )
    before_payload = path.read_bytes().split(b"\n\n", 1)[1]

    changed = repair.repair_nrrd_space_units(path)

    after_payload = path.read_bytes().split(b"\n\n", 1)[1]
    repaired, header = nrrd.read(str(path), index_order="C")
    assert changed is True
    assert after_payload == before_payload
    np.testing.assert_array_equal(repaired, data)
    assert repaired.dtype == data.dtype
    np.testing.assert_array_equal(
        header["space directions"],
        np.array(
            [
                [1.0, 0.0, 0.0],
                [0.0, 2.0, 0.0],
                [0.0, 0.0, 3.0],
            ]
        ),
    )
    assert header["space units"] == ["microns", "microns", "microns"]


def test_repair_nrrd_space_units_dry_run_does_not_write(tmp_path):
    repair = _load_repair_module()
    path = tmp_path / "sample.nrrd"
    path.write_bytes(
        b'NRRD0005\nspace units: "um" "um" "um"\nencoding: raw\n\npayload'
    )
    before = path.read_bytes()

    changed = repair.repair_nrrd_space_units(path, dry_run=True)

    assert changed is True
    assert path.read_bytes() == before
