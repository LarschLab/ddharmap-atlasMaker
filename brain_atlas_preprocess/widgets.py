from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem, QWidget

from .model import StackFileState


STATUS_COLORS = {
    "unreviewed": QColor("#fff7d6"),
    "reviewed_no_rotation": QColor("#dceee2"),
    "rotation_planned": QColor("#dce7ff"),
}

PREVIEW_LUTS = {
    488: (0, 255, 0),
    546: (255, 255, 0),
    647: (255, 0, 0),
}


class StackFileList(QListWidget):
    pathsDropped = Signal(list)
    deletePressed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

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

    def selected_paths(self) -> list[str]:
        return [
            str(item.data(Qt.ItemDataRole.UserRole))
            for item in self.selectedItems()
        ]

    def dragEnterEvent(self, event: Any) -> None:
        if _dropped_local_paths(event.mimeData()):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event: Any) -> None:
        if _dropped_local_paths(event.mimeData()):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event: Any) -> None:
        paths = _dropped_local_paths(event.mimeData())
        if not paths:
            super().dropEvent(event)
            return
        self.pathsDropped.emit(paths)
        event.acceptProposedAction()

    def keyPressEvent(self, event: Any) -> None:
        if event.key() in {Qt.Key.Key_Delete, Qt.Key.Key_Backspace}:
            self.deletePressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)


def dropped_stack_paths(paths: list[str]) -> tuple[list[str], list[str]]:
    stack_paths: list[str] = []
    skipped: list[str] = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_dir():
            children = sorted(path.iterdir())
            lsm_children = [
                str(child)
                for child in children
                if child.is_file() and child.suffix.lower() == ".lsm"
            ]
            if lsm_children:
                stack_paths.extend(lsm_children)
            else:
                skipped.append(str(path))
        elif path.is_file() and path.suffix.lower() == ".lsm":
            stack_paths.append(str(path))
        else:
            skipped.append(str(path))
    return stack_paths, skipped


def _dropped_local_paths(mime_data: Any) -> list[str]:
    if mime_data is None or not mime_data.hasUrls():
        return []
    paths: list[str] = []
    for url in mime_data.urls():
        if not url.isLocalFile():
            continue
        local_path = url.toLocalFile()
        if local_path:
            paths.append(local_path)
    return paths


class ChannelThumbnail(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._image: np.ndarray | None = None
        self._wavelength_nm: int | None = None
        self._pixmap: QPixmap | None = None
        self._message = "Preview unavailable"
        self.setFixedSize(140, 110)

    def set_image(
        self, image: np.ndarray | None, wavelength_nm: int | None = None
    ) -> None:
        self._image = image
        self._wavelength_nm = wavelength_nm
        self._refresh_pixmap()
        self.update()

    def set_wavelength(self, wavelength_nm: int | None) -> None:
        self._wavelength_nm = wavelength_nm
        self._refresh_pixmap()
        self.update()

    def _refresh_pixmap(self) -> None:
        self._pixmap = (
            None
            if self._image is None
            else _array_to_pixmap(self._image, self._wavelength_nm)
        )

    def set_message(self, message: str) -> None:
        self._message = message
        self.update()

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#15171a"))
        if self._pixmap is None:
            painter.setPen(QPen(QColor("#c8ced8")))
            painter.drawText(
                self.rect().adjusted(8, 8, -8, -8),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                self._message,
            )
            return

        available = self.rect().adjusted(4, 4, -4, -4)
        scaled = self._pixmap.scaled(
            available.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        target_x = available.center().x() - scaled.width() // 2
        target_y = available.center().y() - scaled.height() // 2
        painter.drawPixmap(target_x, target_y, scaled)


class RotationPreview(QWidget):
    angleChanged = Signal(float)
    cropCenterChanged = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._angle = 0.0
        self._crop_size_px = 750
        self._crop_center_yx: tuple[int, int] | None = None
        self._drag_start_angle: float | None = None
        self._drag_start_rotation = 0.0
        self.setMinimumSize(520, 520)
        self.setMouseTracking(True)

    def set_image(
        self, image: np.ndarray | None, wavelength_nm: int | None = None
    ) -> None:
        self._pixmap = (
            None if image is None else _array_to_pixmap(image, wavelength_nm)
        )
        self.update()

    def set_angle(self, angle: float) -> None:
        self._angle = angle
        self.update()

    def set_crop_size(self, size_px: int) -> None:
        self._crop_size_px = max(1, int(size_px))
        self.update()

    def set_crop_center(self, center_yx: tuple[int, int] | None) -> None:
        self._crop_center_yx = center_yx
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

        self._draw_crop_overlay(painter, center, scaled)

        painter.setPen(QPen(QColor("#ffffff")))
        painter.drawText(
            self.rect().adjusted(12, 12, -12, -12),
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
            f"{self._angle:.2f} deg",
        )

    def mousePressEvent(self, event: Any) -> None:
        if self._pixmap is None:
            return
        if event.button() == Qt.MouseButton.RightButton:
            self._drag_start_angle = self._point_angle(event.position().toPoint())
            self._drag_start_rotation = self._angle
        elif event.button() == Qt.MouseButton.LeftButton:
            center_yx = self._widget_point_to_rotated_center(
                event.position().toPoint()
            )
            self._crop_center_yx = center_yx
            self.cropCenterChanged.emit(center_yx)
            self.update()

    def mouseMoveEvent(self, event: Any) -> None:
        if self._drag_start_angle is None:
            return
        current = self._point_angle(event.position().toPoint())
        self._angle = self._drag_start_rotation + (current - self._drag_start_angle)
        self.angleChanged.emit(self._angle)
        self.update()

    def mouseReleaseEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self._drag_start_angle = None

    def _point_angle(self, point: QPoint) -> float:
        center = self.rect().center()
        dy = point.y() - center.y()
        dx = point.x() - center.x()
        return math.degrees(math.atan2(dy, dx))

    def _scaled_image_rect(self) -> QRectF | None:
        if self._pixmap is None:
            return None
        available = self.rect().adjusted(12, 12, -12, -12)
        scaled = self._pixmap.scaled(
            available.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        center = available.center()
        return QRectF(
            center.x() - scaled.width() / 2,
            center.y() - scaled.height() / 2,
            scaled.width(),
            scaled.height(),
        )

    def _widget_point_to_rotated_center(self, point: QPoint) -> tuple[int, int]:
        image_rect = self._scaled_image_rect()
        if self._pixmap is None or image_rect is None:
            return (0, 0)
        scale = image_rect.width() / self._pixmap.width()
        rotated_h, rotated_w = _rotated_shape_yx(
            self._pixmap.height(), self._pixmap.width(), self._angle
        )
        center_x = (point.x() - image_rect.center().x()) / scale + rotated_w / 2
        center_y = (point.y() - image_rect.center().y()) / scale + rotated_h / 2
        return (int(round(center_y)), int(round(center_x)))

    def _draw_crop_overlay(
        self,
        painter: QPainter,
        image_center: QPoint,
        scaled: QPixmap,
    ) -> None:
        if self._pixmap is None:
            return
        scale = scaled.width() / self._pixmap.width()
        rotated_h, rotated_w = _rotated_shape_yx(
            self._pixmap.height(), self._pixmap.width(), self._angle
        )
        center_y, center_x = self._crop_center_yx or (rotated_h // 2, rotated_w // 2)
        overlay_center_x = image_center.x() + (center_x - rotated_w / 2) * scale
        overlay_center_y = image_center.y() + (center_y - rotated_h / 2) * scale
        side = self._crop_size_px * scale

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setPen(QPen(QColor("#19d3ff"), 2, Qt.PenStyle.SolidLine))
        painter.drawRect(
            QRectF(
                overlay_center_x - side / 2,
                overlay_center_y - side / 2,
                side,
                side,
            )
        )
        painter.setPen(QPen(QColor("#ffffff"), 1))
        painter.drawLine(
            int(overlay_center_x - 6),
            int(overlay_center_y),
            int(overlay_center_x + 6),
            int(overlay_center_y),
        )
        painter.drawLine(
            int(overlay_center_x),
            int(overlay_center_y - 6),
            int(overlay_center_x),
            int(overlay_center_y + 6),
        )
        painter.restore()


def _rotated_shape_yx(height: int, width: int, angle_degrees: float) -> tuple[int, int]:
    angle = math.radians(angle_degrees)
    cosine = abs(math.cos(angle))
    sine = abs(math.sin(angle))
    rotated_height = int(height * cosine + width * sine + 0.5)
    rotated_width = int(width * cosine + height * sine + 0.5)
    return max(1, rotated_height), max(1, rotated_width)


def _array_to_pixmap(
    image: np.ndarray, wavelength_nm: int | None = None
) -> QPixmap:
    normalized = _normalize_preview_image(image)
    lut_color = PREVIEW_LUTS.get(wavelength_nm)
    if lut_color is None:
        return _grayscale_pixmap(normalized)
    return _lut_pixmap(normalized, lut_color)


def _normalize_preview_image(image: np.ndarray) -> np.ndarray:
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
    return normalized


def _grayscale_pixmap(normalized: np.ndarray) -> QPixmap:
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


def _lut_pixmap(normalized: np.ndarray, color: tuple[int, int, int]) -> QPixmap:
    height, width = normalized.shape
    rgb = np.empty((height, width, 3), dtype=np.uint8)
    for channel, value in enumerate(color):
        rgb[:, :, channel] = ((normalized.astype(np.uint16) * value) // 255).astype(
            np.uint8
        )
    contiguous = np.ascontiguousarray(rgb)
    image_qt = QImage(
        contiguous.data,
        width,
        height,
        contiguous.strides[0],
        QImage.Format.Format_RGB888,
    ).copy()
    return QPixmap.fromImage(image_qt)
