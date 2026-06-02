from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QAbstractItemView, QApplication

from brain_atlas_preprocess.model import StackFileState
from brain_atlas_preprocess.widgets import (
    StackFileList,
    _array_to_pixmap,
    dropped_stack_paths,
)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _bright_pixel(wavelength_nm: int | None) -> tuple[int, int, int]:
    _app()
    pixmap = _array_to_pixmap(
        np.array([[0, 0], [0, 100]], dtype=np.uint8),
        wavelength_nm,
    )
    color = pixmap.toImage().pixelColor(1, 1)
    return color.red(), color.green(), color.blue()


def test_preview_lut_tints_488_green() -> None:
    red, green, blue = _bright_pixel(488)

    assert green == 255
    assert red == 0
    assert blue == 0


def test_preview_lut_tints_546_yellow() -> None:
    red, green, blue = _bright_pixel(546)

    assert red == 255
    assert green == 255
    assert blue == 0


def test_preview_lut_tints_647_red() -> None:
    red, green, blue = _bright_pixel(647)

    assert red == 255
    assert green == 0
    assert blue == 0


def test_preview_lut_keeps_unknown_wavelength_grayscale() -> None:
    red, green, blue = _bright_pixel(740)

    assert red == green == blue == 255


def test_stack_file_list_uses_extended_selection() -> None:
    _app()
    file_list = StackFileList()

    assert (
        file_list.selectionMode()
        == QAbstractItemView.SelectionMode.ExtendedSelection
    )


def test_stack_file_list_reports_selected_paths() -> None:
    _app()
    file_list = StackFileList()
    file_list.set_files([
        StackFileState(path="/tmp/a.lsm"),
        StackFileState(path="/tmp/b.lsm"),
    ])

    file_list.item(0).setSelected(True)
    file_list.item(1).setSelected(True)

    assert file_list.selected_paths() == ["/tmp/a.lsm", "/tmp/b.lsm"]


def test_stack_file_list_emits_delete_for_delete_and_backspace() -> None:
    _app()
    file_list = StackFileList()
    emitted: list[str] = []
    file_list.deletePressed.connect(lambda: emitted.append("delete"))

    for key in [Qt.Key.Key_Delete, Qt.Key.Key_Backspace]:
        event = QKeyEvent(
            QEvent.Type.KeyPress,
            key,
            Qt.KeyboardModifier.NoModifier,
        )
        file_list.keyPressEvent(event)

    assert emitted == ["delete", "delete"]


def test_dropped_stack_paths_accepts_lsm_files_and_one_level_folders(tmp_path):
    direct = tmp_path / "direct.lsm"
    direct.write_text("", encoding="utf-8")
    ignored = tmp_path / "ignored.txt"
    ignored.write_text("", encoding="utf-8")
    folder = tmp_path / "folder"
    folder.mkdir()
    child = folder / "child.lsm"
    child.write_text("", encoding="utf-8")
    nested = folder / "nested"
    nested.mkdir()
    nested_child = nested / "nested_child.lsm"
    nested_child.write_text("", encoding="utf-8")

    stacks, skipped = dropped_stack_paths([
        str(ignored),
        str(folder),
        str(direct),
    ])

    assert stacks == [str(child), str(direct)]
    assert skipped == [str(ignored)]
