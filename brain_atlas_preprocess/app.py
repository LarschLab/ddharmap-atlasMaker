from __future__ import annotations

from pathlib import Path
import sys
import traceback
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QProgressBar,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from brain_atlas_preprocess.io import (
    StackFormatError,
    build_channel_mapping_suggestions,
    export_preprocessed_channels,
    load_labeled_channel_mip,
    make_file_state,
    read_unlabeled_lsm_metadata,
    validate_channel_mapping,
)
from brain_atlas_preprocess.model import (
    PROJECT_FILENAME,
    ChannelInfo,
    ProjectState,
    StackFileState,
)
from brain_atlas_preprocess.widgets import RotationPreview, StackFileList


class PreviewWorker(QObject):
    finished = Signal(str, int, object)
    failed = Signal(str, int, str)

    def __init__(
        self,
        path: str,
        channels: list[ChannelInfo],
        channel_index: int,
    ) -> None:
        super().__init__()
        self.path = path
        self.channels = channels
        self.channel_index = channel_index

    @Slot()
    def run(self) -> None:
        try:
            image = load_labeled_channel_mip(
                self.path,
                self.channels,
                self.channel_index,
            )
            self.finished.emit(self.path, self.channel_index, image)
        except Exception as exc:
            self.failed.emit(self.path, self.channel_index, _format_error(exc))


class PreprocessWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(list)
    failed = Signal(str)

    def __init__(
        self,
        files: list[StackFileState],
        output_root: str,
        crop_size_px: int,
    ) -> None:
        super().__init__()
        self.files = files
        self.output_root = output_root
        self.crop_size_px = crop_size_px

    @Slot()
    def run(self) -> None:
        outputs: list[str] = []
        try:
            total = len(self.files)
            for index, file_state in enumerate(self.files, start=1):
                self.progress.emit(index - 1, total, file_state.name)
                output_dir = export_preprocessed_channels(
                    file_state,
                    self.output_root,
                    interpolation="linear",
                    expand_canvas=True,
                    crop_size_px=self.crop_size_px,
                )
                outputs.append(str(output_dir))
                self.progress.emit(index, total, file_state.name)
            self.finished.emit(outputs)
        except Exception as exc:
            self.failed.emit(_format_error(exc))


class ChannelMappingDialog(QDialog):
    def __init__(
        self,
        path: str,
        channels: list[ChannelInfo],
        bridge_channel_index: int | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Channels: {Path(path).name}")
        self._name_inputs: list[QLineEdit] = []
        self._wavelength_inputs: list[QSpinBox] = []
        self._bridge_group = QButtonGroup(self)
        self._bridge_group.setExclusive(True)
        self.channels: list[ChannelInfo] = []
        self.bridge_channel_index: int | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Set channel labels and choose the bridge channel."))

        selected_bridge = bridge_channel_index
        if selected_bridge is None:
            for channel in channels:
                if channel.gene == "DAPI" and channel.wavelength_nm == 740:
                    selected_bridge = channel.index
                    break
        if selected_bridge is None and channels:
            selected_bridge = channels[-1].index

        for channel in channels:
            row = QHBoxLayout()
            row.addWidget(QLabel(f"Channel {channel.index + 1}"))

            name_input = QLineEdit(channel.gene)
            row.addWidget(name_input, stretch=1)
            self._name_inputs.append(name_input)

            wavelength_input = QSpinBox()
            wavelength_input.setRange(1, 100000)
            wavelength_input.setValue(channel.wavelength_nm)
            wavelength_input.setSuffix(" nm")
            row.addWidget(wavelength_input)
            self._wavelength_inputs.append(wavelength_input)

            bridge = QRadioButton("Bridge")
            bridge.setChecked(channel.index == selected_bridge)
            self._bridge_group.addButton(bridge, channel.index)
            row.addWidget(bridge)
            layout.addLayout(row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @Slot()
    def _accept_if_valid(self) -> None:
        try:
            channels = validate_channel_mapping(
                [
                    ChannelInfo(
                        index=index,
                        gene=name_input.text(),
                        wavelength_nm=wavelength_input.value(),
                    )
                    for index, (name_input, wavelength_input) in enumerate(
                        zip(self._name_inputs, self._wavelength_inputs)
                    )
                ],
                len(self._name_inputs),
            )
            bridge_index = self._bridge_group.checkedId()
            if bridge_index < 0:
                raise StackFormatError("Choose one bridge channel.")
        except StackFormatError as exc:
            QMessageBox.warning(self, "Invalid channel mapping", str(exc))
            return
        self.channels = channels
        self.bridge_channel_index = bridge_index
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.project = ProjectState()
        self.current_file: StackFileState | None = None
        self.preview_cache: dict[tuple[str, int], object] = {}
        self.pending_preview: tuple[str, int] | None = None
        self.preview_thread: QThread | None = None
        self.preview_worker: PreviewWorker | None = None
        self.preprocess_thread: QThread | None = None
        self.preprocess_worker: PreprocessWorker | None = None

        self.setWindowTitle("Brain Atlas Preprocess")
        self.resize(1180, 760)
        self.setStatusBar(QStatusBar())

        self.file_list = StackFileList()
        self.file_list.currentItemChanged.connect(self._selected_file_changed)

        self.preview = RotationPreview()
        self.preview.angleChanged.connect(self._angle_changed)
        self.preview.cropCenterChanged.connect(self._crop_center_changed)

        self.output_label = QLabel("No output root selected")
        self.angle_label = QLabel("Angle: 0.00 deg")
        self.channel_label = QLabel("Channel: -")
        self.crop_label = QLabel("Crop size")
        self.crop_size_input = QSpinBox()
        self.crop_size_input.setRange(1, 100000)
        self.crop_size_input.setValue(self.project.crop_size_px)
        self.crop_size_input.setSuffix(" px")
        self.crop_size_input.valueChanged.connect(self._crop_size_changed)
        self.progress = QProgressBar()
        self.progress.setVisible(False)

        self._build_layout()
        self._install_shortcuts()

    def _build_layout(self) -> None:
        add_files = QPushButton("Add Stacks")
        add_files.clicked.connect(self._add_files)
        open_project = QPushButton("Open Project")
        open_project.clicked.connect(self._open_project)
        output_root = QPushButton("Output Root")
        output_root.clicked.connect(self._select_output_root)
        reset = QPushButton("Reset Rotation")
        reset.clicked.connect(self._reset_rotation)
        previous_file = QPushButton("Previous")
        previous_file.clicked.connect(lambda: self._move_selection(-1))
        next_file = QPushButton("Next")
        next_file.clicked.connect(lambda: self._move_selection(1))
        previous_channel = QPushButton("Prev Channel")
        previous_channel.clicked.connect(lambda: self._cycle_channel(-1))
        next_channel = QPushButton("Next Channel")
        next_channel.clicked.connect(lambda: self._cycle_channel(1))
        edit_channels = QPushButton("Channels...")
        edit_channels.clicked.connect(self._edit_current_channels)
        preprocess = QPushButton("Preprocess")
        preprocess.clicked.connect(self._preprocess)

        left_controls = QHBoxLayout()
        left_controls.addWidget(add_files)
        left_controls.addWidget(open_project)
        left_controls.addWidget(output_root)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addLayout(left_controls)
        left_layout.addWidget(self.output_label)
        left_layout.addWidget(self.file_list)

        right_controls = QHBoxLayout()
        right_controls.addWidget(previous_file)
        right_controls.addWidget(next_file)
        right_controls.addWidget(previous_channel)
        right_controls.addWidget(next_channel)
        right_controls.addWidget(edit_channels)
        right_controls.addWidget(preprocess)
        right_controls.addStretch(1)

        right_settings = QHBoxLayout()
        right_settings.addWidget(reset)
        right_settings.addStretch(1)
        right_settings.addWidget(self.crop_label)
        right_settings.addWidget(self.crop_size_input)
        right_settings.addWidget(self.channel_label)
        right_settings.addWidget(self.angle_label)

        right_toolbar = QVBoxLayout()
        right_toolbar.addLayout(right_controls)
        right_toolbar.addLayout(right_settings)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addLayout(right_toolbar)
        right_layout.addWidget(self.preview, stretch=1)
        right_layout.addWidget(self.progress)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

    def _install_shortcuts(self) -> None:
        shortcuts = [
            ("Previous stack", "q", lambda: self._move_selection(-1)),
            ("Next stack", "e", lambda: self._move_selection(1)),
            ("Previous channel", "a", lambda: self._cycle_channel(-1)),
            ("Next channel", "d", lambda: self._cycle_channel(1)),
        ]
        for text, key, callback in shortcuts:
            action = QAction(text, self)
            action.setShortcut(QKeySequence(key))
            action.triggered.connect(callback)
            self.addAction(action)

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select LSM stacks",
            str(Path.home()),
            "LSM stacks (*.lsm);;All files (*)",
        )
        if not paths:
            return
        errors: list[str] = []
        for path in paths:
            try:
                file_state = make_file_state(path)
                self.project.add_or_update_file(file_state)
            except StackFormatError as exc:
                try:
                    file_state = self._file_state_from_channel_dialog(path)
                except StackFormatError as fallback_exc:
                    errors.append(f"{exc}\n{fallback_exc}")
                    continue
                if file_state is not None:
                    self.project.add_or_update_file(file_state)
        self._refresh_file_list()
        self._save_project_if_possible()
        if self.file_list.count() and self.file_list.currentRow() < 0:
            self.file_list.setCurrentRow(0)
        if errors:
            QMessageBox.warning(self, "Some files were skipped", "\n\n".join(errors))

    def _file_state_from_channel_dialog(
        self,
        path: str,
        existing: StackFileState | None = None,
    ) -> StackFileState | None:
        metadata = read_unlabeled_lsm_metadata(path)
        channels = existing.channels if existing is not None else metadata.channels
        if len(channels) != int(metadata.shape[1]):
            channels = build_channel_mapping_suggestions(path, int(metadata.shape[1]))
        bridge_index = (
            existing.resolved_bridge_channel_index()
            if existing is not None
            else metadata.channels[-1].index
        )
        dialog = ChannelMappingDialog(path, channels, bridge_index, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return make_file_state(
            path,
            channels=dialog.channels,
            bridge_channel_index=dialog.bridge_channel_index,
        )

    def _open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open project",
            str(Path.home()),
            "Brain Atlas project (*.json);;All files (*)",
        )
        if not path:
            return
        try:
            self.project = ProjectState.load(path)
        except Exception as exc:
            QMessageBox.critical(self, "Could not open project", _format_error(exc))
            return
        self.preview_cache.clear()
        self.crop_size_input.setValue(self.project.crop_size_px)
        self.preview.set_crop_size(self.project.crop_size_px)
        self._refresh_file_list()
        self._update_output_label()
        if self.file_list.count():
            self.file_list.setCurrentRow(0)

    def _select_output_root(self) -> None:
        root = QFileDialog.getExistingDirectory(
            self,
            "Select output root",
            self.project.output_root or str(Path.home()),
        )
        if not root:
            return
        self.project.output_root = root
        self._update_output_label()
        self._save_project_if_possible()

    def _selected_file_changed(self, current: Any, previous: Any) -> None:
        if current is None:
            self.current_file = None
            self.preview.set_image(None)
            self.preview.set_angle(0.0)
            self.preview.set_crop_center(None)
            self.angle_label.setText("Angle: 0.00 deg")
            self.channel_label.setText("Channel: -")
            return
        path = current.data(Qt.ItemDataRole.UserRole)
        self.current_file = self.project.get_file(path)
        if self.current_file is None:
            return
        self._ensure_bridge_channel_index(self.current_file)
        self.preview.set_angle(self.current_file.rotation_degrees)
        self.preview.set_crop_size(self.project.crop_size_px)
        self.preview.set_crop_center(self.current_file.crop_center_yx)
        self.angle_label.setText(f"Angle: {self.current_file.rotation_degrees:.2f} deg")
        self._update_channel_label()
        channel_index = self.current_file.resolved_bridge_channel_index()
        if channel_index is None:
            self.preview.set_image(None)
            return
        cache_key = (path, channel_index)
        if cache_key in self.preview_cache:
            self.preview.set_image(self.preview_cache[cache_key])
            return
        self.statusBar().showMessage(
            f"Loading channel {channel_index + 1} preview: {Path(path).name}"
        )
        self.preview.set_image(None)
        self._start_preview_worker(path, channel_index)

    def _start_preview_worker(self, path: str, channel_index: int) -> None:
        if self.preview_thread is not None and self.preview_thread.isRunning():
            self.pending_preview = (path, channel_index)
            self.statusBar().showMessage("Preview load queued", 1500)
            return
        self.preview_thread = QThread()
        file_state = self.project.get_file(path)
        if file_state is None:
            return
        self.preview_worker = PreviewWorker(
            path,
            list(file_state.channels),
            channel_index,
        )
        self.preview_worker.moveToThread(self.preview_thread)
        self.preview_thread.started.connect(self.preview_worker.run)
        self.preview_worker.finished.connect(self._preview_loaded)
        self.preview_worker.failed.connect(self._preview_failed)
        self.preview_worker.finished.connect(self.preview_thread.quit)
        self.preview_worker.failed.connect(self.preview_thread.quit)
        self.preview_worker.finished.connect(self.preview_worker.deleteLater)
        self.preview_worker.failed.connect(self.preview_worker.deleteLater)
        self.preview_thread.finished.connect(self.preview_thread.deleteLater)
        self.preview_thread.finished.connect(self._preview_thread_finished)
        self.preview_thread.start()

    @Slot()
    def _preview_thread_finished(self) -> None:
        self.preview_thread = None
        self.preview_worker = None
        if self.pending_preview is None:
            return
        path, channel_index = self.pending_preview
        self.pending_preview = None
        if (
            self.current_file
            and self.current_file.path == path
            and self.current_file.resolved_bridge_channel_index() == channel_index
        ):
            self._start_preview_worker(path, channel_index)

    @Slot(str, int, object)
    def _preview_loaded(self, path: str, channel_index: int, image: object) -> None:
        self.preview_cache[(path, channel_index)] = image
        if (
            self.current_file
            and self.current_file.path == path
            and self.current_file.resolved_bridge_channel_index() == channel_index
        ):
            self.preview.set_image(image)
        self.statusBar().showMessage("Preview loaded", 2500)

    @Slot(str, int, str)
    def _preview_failed(self, path: str, channel_index: int, message: str) -> None:
        if (
            self.current_file
            and self.current_file.path == path
            and self.current_file.resolved_bridge_channel_index() == channel_index
        ):
            self.preview.set_image(None)
        QMessageBox.critical(self, "Could not load preview", message)

    def _angle_changed(self, angle: float) -> None:
        if self.current_file is None:
            return
        self.current_file.rotation_degrees = angle
        self.current_file.reviewed = True
        self.angle_label.setText(f"Angle: {angle:.2f} deg")
        self.file_list.refresh_file(self.current_file)
        self._save_project_if_possible()

    def _crop_center_changed(self, center_yx: object) -> None:
        if self.current_file is None:
            return
        y, x = center_yx
        self.current_file.crop_center_yx = (int(y), int(x))
        self.current_file.reviewed = True
        self.file_list.refresh_file(self.current_file)
        self._save_project_if_possible()

    def _crop_size_changed(self, size_px: int) -> None:
        self.project.crop_size_px = int(size_px)
        self.preview.set_crop_size(size_px)
        self._save_project_if_possible()

    def _cycle_channel(self, delta: int) -> None:
        if self.current_file is None or not self.current_file.channels:
            return
        current_index = self.current_file.resolved_bridge_channel_index()
        if current_index is None:
            current_position = 0
        else:
            channel_indices = [channel.index for channel in self.current_file.channels]
            current_position = channel_indices.index(current_index)
        next_position = (current_position + delta) % len(self.current_file.channels)
        self.current_file.bridge_channel_index = self.current_file.channels[
            next_position
        ].index
        self._update_channel_label()
        self.preview.set_image(None)
        self._save_project_if_possible()
        path = self.current_file.path
        channel_index = self.current_file.bridge_channel_index
        if channel_index is None:
            return
        cache_key = (path, channel_index)
        if cache_key in self.preview_cache:
            self.preview.set_image(self.preview_cache[cache_key])
            return
        self._start_preview_worker(path, channel_index)

    def _edit_current_channels(self) -> None:
        if self.current_file is None:
            return
        file_state = self._file_state_from_channel_dialog(
            self.current_file.path,
            existing=self.current_file,
        )
        if file_state is None:
            return
        file_state.rotation_degrees = self.current_file.rotation_degrees
        file_state.reviewed = self.current_file.reviewed
        file_state.crop_center_yx = self.current_file.crop_center_yx
        self.project.add_or_update_file(file_state)
        self.current_file = file_state
        self.preview_cache = {
            key: value
            for key, value in self.preview_cache.items()
            if key[0] != file_state.path
        }
        self._refresh_file_list()
        self._update_channel_label()
        self._save_project_if_possible()
        channel_index = file_state.resolved_bridge_channel_index()
        if channel_index is not None:
            self.preview.set_image(None)
            self._start_preview_worker(file_state.path, channel_index)

    def _ensure_bridge_channel_index(self, file_state: StackFileState) -> None:
        resolved = file_state.resolved_bridge_channel_index()
        if resolved is not None and file_state.bridge_channel_index != resolved:
            file_state.bridge_channel_index = resolved

    def _update_channel_label(self) -> None:
        if self.current_file is None:
            self.channel_label.setText("Channel: -")
            return
        channel_index = self.current_file.resolved_bridge_channel_index()
        channel = next(
            (
                item
                for item in self.current_file.channels
                if item.index == channel_index
            ),
            None,
        )
        if channel is None:
            self.channel_label.setText("Channel: -")
            return
        self.channel_label.setText(
            f"Channel: {channel.index + 1}/{len(self.current_file.channels)} "
            f"{channel.label}"
        )

    def _reset_rotation(self) -> None:
        if self.current_file is None:
            return
        self.current_file.rotation_degrees = 0.0
        self.current_file.reviewed = True
        self.preview.set_angle(0.0)
        self.angle_label.setText("Angle: 0.00 deg")
        self.file_list.refresh_file(self.current_file)
        self._save_project_if_possible()

    def _move_selection(self, delta: int) -> None:
        if not self.file_list.count():
            return
        row = self.file_list.currentRow()
        if row < 0:
            row = 0
        else:
            row = max(0, min(self.file_list.count() - 1, row + delta))
        self.file_list.setCurrentRow(row)

    def _preprocess(self) -> None:
        if not self.project.output_root:
            QMessageBox.warning(self, "Output root required", "Select an output root first.")
            return
        if not self.project.files:
            QMessageBox.warning(self, "No stacks selected", "Add at least one LSM stack first.")
            return
        unreviewed = [file_state.name for file_state in self.project.files if not file_state.reviewed]
        if unreviewed:
            response = QMessageBox.question(
                self,
                "Unreviewed stacks",
                "Some stacks are still unreviewed. Continue with zero-degree rotation "
                "for any unreviewed stacks?",
            )
            if response != QMessageBox.StandardButton.Yes:
                return
        self._save_project_if_possible()
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.preprocess_thread = QThread()
        self.preprocess_worker = PreprocessWorker(
            list(self.project.files),
            self.project.output_root,
            self.project.crop_size_px,
        )
        self.preprocess_worker.moveToThread(self.preprocess_thread)
        self.preprocess_thread.started.connect(self.preprocess_worker.run)
        self.preprocess_worker.progress.connect(self._preprocess_progress)
        self.preprocess_worker.finished.connect(self._preprocess_finished)
        self.preprocess_worker.failed.connect(self._preprocess_failed)
        self.preprocess_worker.finished.connect(self.preprocess_thread.quit)
        self.preprocess_worker.failed.connect(self.preprocess_thread.quit)
        self.preprocess_worker.finished.connect(self.preprocess_worker.deleteLater)
        self.preprocess_worker.failed.connect(self.preprocess_worker.deleteLater)
        self.preprocess_thread.finished.connect(self.preprocess_thread.deleteLater)
        self.preprocess_thread.finished.connect(self._preprocess_thread_finished)
        self.preprocess_thread.start()

    @Slot()
    def _preprocess_thread_finished(self) -> None:
        self.preprocess_thread = None
        self.preprocess_worker = None

    @Slot(int, int, str)
    def _preprocess_progress(self, done: int, total: int, name: str) -> None:
        self.progress.setMaximum(total)
        self.progress.setValue(done)
        self.statusBar().showMessage(f"Preprocessing {name} ({done}/{total})")

    @Slot(list)
    def _preprocess_finished(self, outputs: list[str]) -> None:
        self.progress.setVisible(False)
        self.statusBar().showMessage("Preprocessing complete", 5000)
        QMessageBox.information(
            self,
            "Preprocessing complete",
            f"Wrote {len(outputs)} preprocessed stack folder(s).",
        )

    @Slot(str)
    def _preprocess_failed(self, message: str) -> None:
        self.progress.setVisible(False)
        QMessageBox.critical(self, "Preprocessing failed", message)

    def _refresh_file_list(self) -> None:
        selected_path = self.current_file.path if self.current_file else None
        self.file_list.set_files(self.project.files)
        if selected_path:
            for row in range(self.file_list.count()):
                item = self.file_list.item(row)
                if item.data(Qt.ItemDataRole.UserRole) == selected_path:
                    self.file_list.setCurrentRow(row)
                    break

    def _save_project_if_possible(self) -> None:
        if not self.project.output_root:
            return
        try:
            path = self.project.save()
            self.statusBar().showMessage(f"Project saved: {path}", 2000)
        except Exception as exc:
            self.statusBar().showMessage(f"Could not save project: {exc}", 5000)

    def _update_output_label(self) -> None:
        if self.project.output_root:
            project_path = Path(self.project.output_root) / PROJECT_FILENAME
            self.output_label.setText(f"Output: {self.project.output_root}\nProject: {project_path}")
        else:
            self.output_label.setText("No output root selected")


def _format_error(exc: Exception) -> str:
    return "".join(traceback.format_exception_only(type(exc), exc)).strip()


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
