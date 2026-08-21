from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, QThread, Qt, QUrl, Signal
from PySide6.QtGui import QCloseEvent, QDesktopServices, QDragEnterEvent, QDropEvent, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from .config import SUPPORTED_EXTENSIONS, bundled_tool, model_is_ready, model_path
from .icon import icon_png
from .workers import ModelDownloadWorker, TranscriptionWorker


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
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(8)
        layout.addWidget(choose, alignment=Qt.AlignmentFlag.AlignCenter)

    def choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose audio or video", "", "Audio and video files (*)")
        if path:
            self.file_selected.emit(Path(path))

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls()
        if len(urls) == 1 and Path(urls[0].toLocalFile()).suffix.lower() in SUPPORTED_EXTENSIONS:
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
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
        self.start_button = QPushButton("Create transcript")
        self.start_button.setObjectName("primary")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.start)
        layout.addWidget(heading)
        layout.addWidget(intro)
        layout.addWidget(self.drop)
        layout.addWidget(self.file_label)
        layout.addLayout(folder_row)
        layout.addWidget(self.progress)
        layout.addWidget(self.status)
        layout.addWidget(self.start_button)
        self.setCentralWidget(root)
        self.setStyleSheet("""
            QWidget { background: #f7f7f5; color: #202421; font: 15px 'Segoe UI'; }
            #heading { font-size: 28px; font-weight: 650; color: #173a2c; }
            #dropArea { border: 2px dashed #8aa598; border-radius: 12px; background: #ffffff; }
            #dropTitle { font-size: 18px; font-weight: 600; }
            QPushButton { padding: 9px 16px; min-height: 20px; border: 1px solid #aab5af; border-radius: 7px; background: white; }
            QPushButton:hover { background: #eef3f0; }
            QPushButton:disabled { color: #8b918e; background: #e5e7e5; }
            #primary { padding: 13px; background: #176b4b; color: white; border: 0; font-weight: 650; }
            #primary:hover { background: #12583d; }
            #status { color: #4a5750; }
            QProgressBar { height: 16px; border: 1px solid #c6cec9; border-radius: 6px; background: white; text-align: center; }
            QProgressBar::chunk { background: #4c9a78; border-radius: 5px; }
        """)

    def select_source(self, path: Path) -> None:
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            QMessageBox.warning(self, "Unsupported file", "Please choose a common audio or video file.")
            return
        self.source = path
        self.file_label.setText(f"Selected: {path.name}")
        if self.output_dir is None:
            remembered = self.settings.value("output_dir", "")
            self.output_dir = Path(remembered) if remembered else path.parent
            self.folder_label.setText(f"Output folder: {self.output_dir}")
        self.start_button.setEnabled(True)

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
            self.source, self.output_dir, model_path(), bundled_tool("ffmpeg"), bundled_tool("whisper-cli")
        )
        self._launch(worker, self._completed)

    def _launch(self, worker, completed) -> None:
        self.thread = QThread(self)
        worker.moveToThread(self.thread)
        self.thread.started.connect(worker.run)
        worker.progress.connect(self._progress)
        worker.completed.connect(completed)
        worker.failed.connect(self._failed)
        self.thread.worker = worker  # keep the worker alive
        self.thread.start()

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

    def _busy(self, busy: bool) -> None:
        self.is_busy = busy
        self.start_button.setEnabled(not busy and self.source is not None)
        self.drop.setEnabled(not busy)
        self.folder_button.setEnabled(not busy)
        if busy:
            self.progress.setValue(0)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.is_busy:
            event.ignore()
            QMessageBox.information(
                self, "Taatik is still working",
                "Please wait for the current download or transcription to finish before closing Taatik.",
            )
            return
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
