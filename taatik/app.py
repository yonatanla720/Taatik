from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QSettings, QThread, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QCloseEvent, QDesktopServices, QDragEnterEvent, QDragLeaveEvent, QDropEvent, QIcon,
    QKeySequence, QPixmap, QShortcut,
)
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from .config import SUPPORTED_EXTENSIONS, bundled_tool, model_is_ready, model_path, whisper_engines
from .core import format_duration, media_duration
from .icon import icon_png
from .workers import ModelDownloadWorker, TranscriptionWorker


_STYLESHEET = """
    QWidget {{ background: {bg}; color: {text}; font: 15px 'Segoe UI'; }}
    #heading {{ font-size: 28px; font-weight: 650; color: {heading}; }}
    #dropArea {{ border: 2px dashed {drop_border}; border-radius: 12px; background: {drop_bg}; }}
    #dropArea[dragActive="true"] {{ border-color: {primary}; background: {drop_active_bg}; }}
    #dropTitle {{ font-size: 18px; font-weight: 600; }}
    QPushButton {{ padding: 9px 16px; min-height: 20px; border: 1px solid {btn_border};
                   border-radius: 7px; background: {btn_bg}; color: {text}; }}
    QPushButton:hover {{ background: {btn_hover}; }}
    QPushButton:disabled {{ color: {btn_disabled_fg}; background: {btn_disabled_bg}; }}
    #primary {{ padding: 13px; background: {primary}; color: white; border: 0; font-weight: 650; }}
    #primary:hover {{ background: {primary_hover}; }}
    #danger {{ padding: 13px; background: {btn_bg}; color: {danger_fg};
               border: 1px solid {danger_border}; font-weight: 650; }}
    #danger:hover {{ background: {danger_hover}; }}
    #danger:disabled {{ color: {btn_disabled_fg}; background: {btn_disabled_bg}; border-color: {btn_border}; }}
    #status {{ color: {muted}; }}
    QProgressBar {{ height: 16px; border: 1px solid {pb_border}; border-radius: 6px;
                    background: {pb_bg}; text-align: center; }}
    QProgressBar::chunk {{ background: {accent}; border-radius: 5px; }}
"""

_LIGHT = {
    "bg": "#f7f7f5", "text": "#202421", "heading": "#173a2c", "muted": "#4a5750",
    "drop_border": "#8aa598", "drop_bg": "#ffffff", "drop_active_bg": "#eaf3ee", "accent": "#4c9a78",
    "btn_border": "#aab5af", "btn_bg": "#ffffff", "btn_hover": "#eef3f0",
    "btn_disabled_fg": "#8b918e", "btn_disabled_bg": "#e5e7e5",
    "primary": "#176b4b", "primary_hover": "#12583d",
    "danger_fg": "#a4322a", "danger_border": "#d8a29d", "danger_hover": "#fbeceb",
    "pb_border": "#c6cec9", "pb_bg": "#ffffff",
}

_DARK = {
    "bg": "#1e211f", "text": "#e6e9e6", "heading": "#7fc9a6", "muted": "#a7b0ab",
    "drop_border": "#4a5a51", "drop_bg": "#262a28", "drop_active_bg": "#24312b", "accent": "#4c9a78",
    "btn_border": "#47514c", "btn_bg": "#2a2f2c", "btn_hover": "#333a36",
    "btn_disabled_fg": "#6b726e", "btn_disabled_bg": "#242725",
    "primary": "#2f9068", "primary_hover": "#35a074",
    "danger_fg": "#e6857b", "danger_border": "#6e4a46", "danger_hover": "#3a2b29",
    "pb_border": "#3a423d", "pb_bg": "#242725",
}


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 32, 48, 64):
        pixmap = QPixmap()
        pixmap.loadFromData(icon_png(size), "PNG")
        icon.addPixmap(pixmap)
    return icon


class DropArea(QFrame):
    file_selected = Signal(object)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("dropArea")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 42, 30, 42)
        title = QLabel("Drop an audio or video file here")
        title.setObjectName("dropTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("or choose a file from your computer")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        choose = QPushButton("Choose file")
        choose.clicked.connect(self.choose_file)
        choose.setMinimumWidth(150)
        choose.setToolTip("Choose a recording (Ctrl+O)")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(8)
        layout.addWidget(choose, alignment=Qt.AlignmentFlag.AlignCenter)

    def choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose audio or video", "", "Audio and video files (*)")
        if path:
            self.file_selected.emit(Path(path))

    def _set_drag_active(self, active: bool) -> None:
        if self.property("dragActive") == active:
            return
        self.setProperty("dragActive", active)
        # Re-evaluate the property-dependent stylesheet rule.
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls()
        if len(urls) == 1 and Path(urls[0].toLocalFile()).suffix.lower() in SUPPORTED_EXTENSIONS:
            self._set_drag_active(True)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._set_drag_active(False)

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_drag_active(False)
        self.file_selected.emit(Path(event.mimeData().urls()[0].toLocalFile()))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.source: Path | None = None
        self.output_dir: Path | None = None
        self.thread: QThread | None = None
        self.is_busy = False
        self.settings = QSettings("Taatik", "Taatik")
        self.setWindowTitle("Taatik — Hebrew Transcription")
        self.resize(680, 560)
        self.setMinimumSize(580, 500)
        self._build_ui()
        geometry = self.settings.value("window_geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(42, 32, 42, 32)
        layout.setSpacing(16)
        heading = QLabel("Hebrew transcription")
        heading.setObjectName("heading")
        intro = QLabel("Turn a recording into text and subtitles. Everything stays on this computer.")
        intro.setWordWrap(True)
        self.drop = DropArea()
        self.drop.file_selected.connect(self.select_source)
        self.file_label = QLabel("No file selected")
        self.file_label.setWordWrap(True)
        folder_row = QHBoxLayout()
        self.folder_label = QLabel("Output folder: not selected")
        self.folder_label.setWordWrap(True)
        self.folder_button = QPushButton("Choose folder")
        self.folder_button.clicked.connect(self.choose_output)
        folder_row.addWidget(self.folder_label, 1)
        folder_row.addWidget(self.folder_button)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status = QLabel("Ready")
        self.status.setObjectName("status")
        self.elapsed_label = QLabel("")
        self.elapsed_label.setObjectName("status")
        self.elapsed_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        status_row = QHBoxLayout()
        status_row.addWidget(self.status, 1)
        status_row.addWidget(self.elapsed_label)
        self._elapsed = QElapsedTimer()
        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self._update_elapsed)
        self.start_button = QPushButton("Create transcript")
        self.start_button.setObjectName("primary")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.start)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setObjectName("danger")
        self.stop_button.clicked.connect(self.cancel)
        self.stop_button.hide()
        layout.addWidget(heading)
        layout.addWidget(intro)
        layout.addWidget(self.drop)
        layout.addWidget(self.file_label)
        layout.addLayout(folder_row)
        layout.addWidget(self.progress)
        layout.addLayout(status_row)
        layout.addWidget(self.start_button)
        layout.addWidget(self.stop_button)
        self.setCentralWidget(root)
        self._apply_theme()
        hints = QApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(lambda _scheme: self._apply_theme())
        self._install_shortcuts()

    def _install_shortcuts(self) -> None:
        QShortcut(QKeySequence.StandardKey.Open, self, activated=self._shortcut_choose)
        for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            QShortcut(QKeySequence(key), self, activated=self._shortcut_start)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self._shortcut_stop)
        self.start_button.setToolTip("Start transcription (Enter)")
        self.stop_button.setToolTip("Stop the current task (Esc)")

    def _shortcut_choose(self) -> None:
        if not self.is_busy:
            self.drop.choose_file()

    def _shortcut_start(self) -> None:
        if self.start_button.isVisible() and self.start_button.isEnabled():
            self.start()

    def _shortcut_stop(self) -> None:
        if self.is_busy and self.stop_button.isEnabled():
            self.cancel()

    def _apply_theme(self) -> None:
        hints = QApplication.styleHints()
        scheme = hints.colorScheme() if hasattr(hints, "colorScheme") else Qt.ColorScheme.Light
        self.setStyleSheet(_STYLESHEET.format(**(_DARK if scheme == Qt.ColorScheme.Dark else _LIGHT)))

    def select_source(self, path: Path) -> None:
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            QMessageBox.warning(self, "Unsupported file", "Please choose a common audio or video file.")
            return
        self.source = path
        self.file_label.setText(f"Selected: {path.name}  ({self._describe(path)})")
        if self.output_dir is None:
            remembered = self.settings.value("output_dir", "")
            self.output_dir = Path(remembered) if remembered else path.parent
            self.folder_label.setText(f"Output folder: {self.output_dir}")
        self.start_button.setEnabled(True)

    def _describe(self, path: Path) -> str:
        try:
            size_mb = path.stat().st_size / (1024 * 1024)
        except OSError:
            return "unavailable"
        details = f"{size_mb:.1f} MB"
        duration = media_duration(bundled_tool("ffmpeg"), path)
        if duration:
            details = f"{format_duration(duration)}, {details}"
        return details

    def choose_output(self) -> None:
        initial = str(self.output_dir or Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Choose output folder", initial)
        if chosen:
            self.output_dir = Path(chosen)
            self.settings.setValue("output_dir", chosen)
            self.folder_label.setText(f"Output folder: {chosen}")

    def start(self) -> None:
        if not self.source or not self.output_dir:
            return
        self._busy(True)
        if not model_is_ready():
            answer = QMessageBox.question(
                self, "Download Hebrew model",
                "Taatik needs to download the Hebrew language model once (about 1.6 GB). "
                "After that, transcription works completely offline. Download it now?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                self._busy(False)
                return
            self._launch(ModelDownloadWorker(model_path()), self._model_ready)
        else:
            self._begin_transcription()

    def _model_ready(self, _path: Path) -> None:
        self._finish_thread()
        self._begin_transcription()

    def _begin_transcription(self) -> None:
        assert self.source and self.output_dir
        worker = TranscriptionWorker(
            self.source, self.output_dir, model_path(), bundled_tool("ffmpeg"), whisper_engines()
        )
        self._launch(worker, self._completed)

    def _launch(self, worker, completed) -> None:
        self.thread = QThread(self)
        worker.moveToThread(self.thread)
        self.thread.started.connect(worker.run)
        worker.progress.connect(self._progress)
        worker.completed.connect(completed)
        worker.failed.connect(self._failed)
        worker.cancelled.connect(self._cancelled)
        self.thread.worker = worker  # keep the worker alive
        self.thread.start()

    def cancel(self) -> None:
        worker = getattr(self.thread, "worker", None) if self.thread else None
        if worker is not None:
            self.stop_button.setEnabled(False)
            self.status.setText("Stopping…")
            worker.cancel()

    def _cancelled(self) -> None:
        self._finish_thread()
        self._busy(False)
        self.progress.setValue(0)
        self.status.setText("Stopped. You can start again when ready.")

    def _progress(self, value: int, message: str) -> None:
        self.progress.setValue(value)
        self.status.setText(message)

    def _completed(self, txt: Path, srt: Path) -> None:
        self._finish_thread()
        self._busy(False)
        self.progress.setValue(100)
        self.status.setText("Done — text and subtitle files were created.")
        message = QMessageBox(self)
        message.setWindowTitle("Transcript ready")
        message.setText(f"Saved {txt.name} and {srt.name}")
        message.setInformativeText(str(txt.parent))
        open_button = message.addButton("Open folder", QMessageBox.ButtonRole.AcceptRole)
        message.addButton("Close", QMessageBox.ButtonRole.RejectRole)
        message.exec()
        if message.clickedButton() is open_button:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(txt.parent)))

    def _failed(self, detail: str) -> None:
        self._finish_thread()
        self._busy(False)
        self.status.setText("Something went wrong. You can try again.")
        QMessageBox.critical(self, "Could not create transcript", detail)

    def _finish_thread(self) -> None:
        if self.thread:
            self.thread.quit()
            self.thread.wait()
            self.thread.deleteLater()
            self.thread = None

    def _update_elapsed(self) -> None:
        self.elapsed_label.setText(format_duration(self._elapsed.elapsed() / 1000))

    def _busy(self, busy: bool) -> None:
        self.is_busy = busy
        self.start_button.setVisible(not busy)
        self.start_button.setEnabled(not busy and self.source is not None)
        self.stop_button.setVisible(busy)
        self.stop_button.setEnabled(busy)
        self.drop.setEnabled(not busy)
        self.folder_button.setEnabled(not busy)
        if busy:
            self.progress.setValue(0)
            self._elapsed.restart()
            self._update_elapsed()
            self._tick.start()
        else:
            self._tick.stop()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.is_busy:
            answer = QMessageBox.question(
                self, "Stop and quit?",
                "Taatik is still working. Stop the current task and quit?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            worker = getattr(self.thread, "worker", None) if self.thread else None
            if worker is not None:
                worker.cancel()
            self._finish_thread()
        self.settings.setValue("window_geometry", self.saveGeometry())
        event.accept()


def main() -> int:
    if sys.platform == "win32":
        os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    app = QApplication(sys.argv)
    app.setApplicationName("Taatik")
    app.setWindowIcon(app_icon())
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
