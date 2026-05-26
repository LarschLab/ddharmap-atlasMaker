from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtWidgets import QApplication

from brain_atlas_preprocess.widgets import _array_to_pixmap


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
