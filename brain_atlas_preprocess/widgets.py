from __future__ import annotations

import math
from typing import Any

import numpy as np

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QWidget

from .model import StackFileState


STATUS_COLORS = {
    "unreviewed": QColor("#fff7d6"),
    "reviewed_no_rotation": QColor("#dceee2"),
    "rotation_planned": QColor("#dce7ff"),
}


class StackFileList(QListWidget):
    def set_files(self, files: list[StackFileState]) -> None:
        self.clear()
        for file_state in files:
            item = QListWidgetItem(file_state.name)
            item.setToolTip(file_state.path)
            item.setData(Qt.ItemDataRole.UserRole, file_state.path)
            self.apply_status(item, file_state)
            self.addItem(item)

    def refresh_file(self, file_state: StackFileState) -> None:
        for row in range(self.count()):
            item = self.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == file_state.path:
                self.apply_status(item, file_state)
                return

    def apply_status(self, item: QListWidgetItem, file_state: StackFileState) -> None:
        item.setBackground(STATUS_COLORS[file_state.status])
        suffix = {
            "unreviewed": "unreviewed",
            "reviewed_no_rotation": "reviewed",
            "rotation_planned": f"{file_state.rotation_degrees:.2f} deg",
        }[file_state.status]
        item.setText(f"{file_state.name}  [{suffix}]")


class RotationPreview(QWidget):
    angleChanged = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._angle = 0.0
        self._drag_start_angle: float | None = None
        self._drag_start_rotation = 0.0
        self.setMinimumSize(520, 520)
        self.setMouseTracking(True)

    def set_image(self, image: np.ndarray | None) -> None:
        self._pixmap = None if image is None else _array_to_pixmap(image)
        self.update()

    def set_angle(self, angle: float) -> None:
        self._angle = angle
        self.update()

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#15171a"))
        if self._pixmap is None:
            painter.setPen(QPen(QColor("#c8ced8")))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No stack selected")
            return

        available = self.rect().adjusted(12, 12, -12, -12)
        scaled = self._pixmap.scaled(
            available.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        center = available.center()
        painter.save()
        painter.translate(center)
        painter.rotate(self._angle)
        painter.drawPixmap(-scaled.width() // 2, -scaled.height() // 2, scaled)
        painter.restore()

        painter.setPen(QPen(QColor("#ffffff")))
        painter.drawText(
            self.rect().adjusted(12, 12, -12, -12),
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
            f"{self._angle:.2f} deg",
        )

    def mousePressEvent(self, event: Any) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._pixmap is None:
            return
        self._drag_start_angle = self._point_angle(event.position().toPoint())
        self._drag_start_rotation = self._angle

    def mouseMoveEvent(self, event: Any) -> None:
        if self._drag_start_angle is None:
            return
        current = self._point_angle(event.position().toPoint())
        self._angle = self._drag_start_rotation + (current - self._drag_start_angle)
        self.angleChanged.emit(self._angle)
        self.update()

    def mouseReleaseEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_angle = None

    def _point_angle(self, point: QPoint) -> float:
        center = self.rect().center()
        dy = point.y() - center.y()
        dx = point.x() - center.x()
        return math.degrees(math.atan2(dy, dx))


def _array_to_pixmap(image: np.ndarray) -> QPixmap:
    array = np.asarray(image)
    if array.ndim != 2:
        raise ValueError(f"Expected 2-D preview image, got {array.shape}.")
    finite = np.nan_to_num(array.astype(np.float32, copy=False))
    low, high = np.percentile(finite, [1, 99.5])
    if high <= low:
        high = float(finite.max()) if finite.size else 1.0
        low = float(finite.min()) if finite.size else 0.0
    if high <= low:
        normalized = np.zeros(finite.shape, dtype=np.uint8)
    else:
        normalized = np.clip((finite - low) / (high - low), 0, 1)
        normalized = (normalized * 255).astype(np.uint8)
    height, width = normalized.shape
    contiguous = np.ascontiguousarray(normalized)
    image_qt = QImage(
        contiguous.data,
        width,
        height,
        contiguous.strides[0],
        QImage.Format.Format_Grayscale8,
    ).copy()
    return QPixmap.fromImage(image_qt)
