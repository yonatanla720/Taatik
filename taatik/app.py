from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QRectF, QSettings, QThread, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QColor, QCloseEvent, QDesktopServices, QDragEnterEvent, QDragLeaveEvent, QDropEvent, QIcon,
    QKeySequence, QPainter, QPixmap, QShortcut,
)
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSpinBox, QTextBrowser,
    QVBoxLayout, QWidget,
)

from . import __version__
from .config import (
    SUPPORTED_EXTENSIONS, bundled_tool, diarization_models, diarization_ready, model_is_ready,
    model_path, whisper_engines,
)
from .core import format_duration, media_duration, output_file, unique_output_base
from .icon import icon_png
from .workers import ModelDownloadWorker, TranscriptionWorker


_STYLESHEET = """
    QWidget {{ background: {bg}; color: {text}; font: 14px 'Segoe UI'; }}
    QLabel, QCheckBox {{ background: transparent; }}
    #appTitle {{ font-size: 23px; font-weight: 700; color: {heading}; }}
    #tagline {{ font-size: 13px; color: {muted}; }}
    #sectionLabel {{ font-size: 12px; font-weight: 700; color: {muted}; letter-spacing: 1px; }}
    #hint {{ font-size: 13px; color: {muted}; }}

    #dropArea {{ border: 2px dashed {border}; border-radius: 18px; background: {surface}; }}
    #dropArea[dragActive="true"] {{ border: 2px solid {accent}; background: {accent_soft}; }}
    #dropTitle {{ font-size: 17px; font-weight: 600; color: {text}; }}
    #dropSub {{ font-size: 13px; color: {muted}; }}

    #card {{ background: {surface}; border: 1px solid {border}; border-radius: 14px; }}
    #divider {{ background: {border}; max-height: 1px; min-height: 1px; border: 0; }}

    QPushButton {{ padding: 8px 16px; min-height: 20px; border: 1px solid {border};
                   border-radius: 9px; background: {surface}; color: {text}; font-weight: 600; }}
    QPushButton:hover {{ background: {chip_bg}; }}
    QPushButton:disabled {{ color: {disabled_fg}; background: {disabled_bg}; border-color: {border}; }}
    #primary {{ padding: 14px 20px; background: {accent}; color: #ffffff; border: 0;
                border-radius: 12px; font-size: 15px; font-weight: 700; }}
    #primary:hover {{ background: {accent_hover}; }}
    #primary:disabled {{ background: {disabled_bg}; color: {disabled_fg}; }}
    #danger {{ padding: 14px 20px; background: {danger_soft}; color: {danger_fg};
               border: 1px solid {danger_border}; border-radius: 12px; font-size: 15px; font-weight: 700; }}
    #danger:hover {{ background: {danger_border}; }}
    #danger:disabled {{ color: {disabled_fg}; background: {disabled_bg}; border-color: {border}; }}

    #status {{ color: {muted}; font-size: 13px; }}
    #linkBtn {{ background: transparent; border: 0; min-height: 0; padding: 2px;
                color: {muted}; font-size: 12px; font-weight: 600; }}
    #linkBtn:hover {{ background: transparent; color: {accent}; }}
    #logView {{ background: {surface}; border: 1px solid {border}; border-radius: 8px;
                color: {muted}; padding: 6px; font-family: 'Consolas','Courier New',monospace;
                font-size: 12px; }}
    QProgressBar {{ min-height: 8px; max-height: 8px; border: 0; border-radius: 4px;
                    background: {chip_bg}; }}
    QProgressBar::chunk {{ background: {accent}; border-radius: 4px; }}

    QCheckBox {{ font-size: 14px; spacing: 9px; }}
    QCheckBox::indicator {{ width: 18px; height: 18px; border: 1.5px solid {border};
                            border-radius: 5px; background: {surface}; }}
    QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; }}
    QCheckBox::indicator:disabled {{ background: {disabled_bg}; border-color: {border}; }}
    QSpinBox {{ padding: 5px 8px; border: 1px solid {border}; border-radius: 8px;
                background: {surface}; color: {text}; min-height: 22px; }}
    QSpinBox:disabled {{ color: {disabled_fg}; background: {disabled_bg}; }}

    QMenuBar {{ background: {bg}; color: {text}; }}
    QMenuBar::item:selected {{ background: {chip_bg}; border-radius: 5px; }}
    QMenu {{ background: {surface}; color: {text}; border: 1px solid {border}; padding: 4px; }}
    QMenu::item {{ padding: 6px 22px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {accent_soft}; }}
"""

_LIGHT = {
    "bg": "#f4f6f4", "surface": "#ffffff", "text": "#17211c", "muted": "#61706a",
    "heading": "#10231a", "border": "#e2e7e3", "accent": "#12855a", "accent_hover": "#0f6f4b",
    "accent_soft": "#e8f3ed", "danger_fg": "#bf3a2d", "danger_soft": "#fbeae8",
    "danger_border": "#edcbc6", "chip_bg": "#eef2ef", "disabled_fg": "#9aa5a0", "disabled_bg": "#eceeec",
}

_DARK = {
    "bg": "#15181a", "surface": "#1e2325", "text": "#e7ecea", "muted": "#97a29d",
    "heading": "#d9e8df", "border": "#2c3331", "accent": "#2ea877", "accent_hover": "#38b785",
    "accent_soft": "#1c332a", "danger_fg": "#e8837a", "danger_soft": "#2e2320",
    "danger_border": "#4e3733", "chip_bg": "#262c2a", "disabled_fg": "#6b746f", "disabled_bg": "#232927",
}


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 32, 48, 64):
        pixmap = QPixmap()
        pixmap.loadFromData(icon_png(size), "PNG")
        icon.addPixmap(pixmap)
    return icon


def logo_pixmap(size: int) -> QPixmap:
    pixmap = QPixmap()
    pixmap.loadFromData(icon_png(size * 2), "PNG")
    pixmap.setDevicePixelRatio(2.0)
    return pixmap


def waveform_glyph(color: str, size: int = 52) -> QPixmap:
    """A small monochrome waveform mark for the drop zone, tinted to the theme."""
    scale = 2
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    dim = size * scale
    heights = (0.36, 0.62, 0.86, 1.0, 0.72, 0.5, 0.3)
    bar = dim * 0.072
    gap = dim * 0.056
    span = len(heights) * bar + (len(heights) - 1) * gap
    x = (dim - span) / 2
    center = dim / 2
    for h in heights:
        half = dim * 0.42 * h
        painter.drawRoundedRect(QRectF(x, center - half, bar, half * 2), bar / 2, bar / 2)
        x += bar + gap
    painter.end()
    pixmap.setDevicePixelRatio(scale)
    return pixmap


class DropArea(QFrame):
    file_selected = Signal(object)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("dropArea")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(160)
        self.setToolTip("Drop a file here, or click to browse (Ctrl+O)")
        self.setAccessibleName("File drop area")
        self.setAccessibleDescription("Drop an audio or video file here, or click to browse.")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 40, 30, 40)
        layout.setSpacing(4)
        self.glyph = QLabel()
        self.glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("Drop audio or video here")
        title.setObjectName("dropTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("or click to browse")
        subtitle.setObjectName("dropSub")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.glyph)
        layout.addSpacing(10)
        layout.addWidget(title)
        layout.addWidget(subtitle)

    def set_accent(self, color: str) -> None:
        self.glyph.setPixmap(waveform_glyph(color))

    def choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose audio or video", "", "Audio and video files (*)")
        if path:
            self.file_selected.emit(Path(path))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.choose_file()

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
        self.resize(720, 660)
        self.setMinimumSize(620, 600)
        self._build_ui()
        geometry = self.settings.value("window_geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 22, 28, 24)
        layout.setSpacing(16)

        # Header: logo + wordmark + tagline.
        self._logo = QLabel()
        self._logo.setPixmap(logo_pixmap(38))
        title = QLabel("Taatik")
        title.setObjectName("appTitle")
        tagline = QLabel("Private Hebrew transcription — audio & video to text, on your device.")
        tagline.setObjectName("tagline")
        tagline.setWordWrap(True)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        titles.addWidget(title)
        titles.addWidget(tagline)
        header = QHBoxLayout()
        header.setSpacing(12)
        header.addWidget(self._logo, 0, Qt.AlignmentFlag.AlignTop)
        header.addLayout(titles, 1)
        layout.addLayout(header)

        # Hero drop zone.
        self.drop = DropArea()
        self.drop.file_selected.connect(self.select_source)
        layout.addWidget(self.drop)
        self.file_label = QLabel("No file selected")
        self.file_label.setObjectName("hint")
        self.file_label.setWordWrap(True)
        layout.addWidget(self.file_label)

        # Settings card: output folder + speaker separation.
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(12)
        self.folder_label = QLabel("Output folder: not selected")
        self.folder_label.setWordWrap(True)
        self.folder_button = QPushButton("Choose folder")
        self.folder_button.clicked.connect(self.choose_output)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_label, 1)
        folder_row.addWidget(self.folder_button)
        divider = QFrame()
        divider.setObjectName("divider")
        self.diar_check = QCheckBox("Separate speakers")
        self.speaker_count = QSpinBox()
        self.speaker_count.setRange(0, 10)
        self.speaker_count.setSpecialValueText("Auto")
        self.speaker_count.setPrefix("Speakers: ")
        self.speaker_count.setEnabled(False)
        self.diar_check.toggled.connect(self.speaker_count.setEnabled)
        if diarization_ready():
            self.diar_check.setToolTip("Label the transcript by speaker (Speaker 1, Speaker 2, …).")
            self.speaker_count.setToolTip("Number of speakers, or Auto to detect.")
        else:
            self.diar_check.setEnabled(False)
            self.diar_check.setToolTip("Speaker separation is unavailable in this build.")
        diar_row = QHBoxLayout()
        diar_row.addWidget(self.diar_check)
        diar_row.addStretch(1)
        diar_row.addWidget(self.speaker_count)
        self.output_preview = QLabel("")
        self.output_preview.setObjectName("hint")
        self.output_preview.setWordWrap(True)
        card_layout.addLayout(folder_row)
        card_layout.addWidget(divider)
        card_layout.addLayout(diar_row)
        card_layout.addWidget(self.output_preview)
        layout.addWidget(card)

        layout.addStretch(1)

        # Progress + status, then the primary action.
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
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

        # Collapsible live log.
        self.log_toggle = QPushButton("Show log")
        self.log_toggle.setObjectName("linkBtn")
        self.log_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.log_toggle.clicked.connect(self._toggle_log)
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("logView")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(4000)
        self.log_view.setFixedHeight(150)
        self.log_view.hide()
        toggle_row = QHBoxLayout()
        toggle_row.addWidget(self.log_toggle)
        toggle_row.addStretch(1)

        layout.addWidget(self.progress)
        layout.addLayout(status_row)
        layout.addLayout(toggle_row)
        layout.addWidget(self.log_view)
        layout.addWidget(self.start_button)
        layout.addWidget(self.stop_button)
        self.setCentralWidget(root)
        if self.settings.value("show_log", False, type=bool):
            self._toggle_log()
        self._setup_accessibility()
        self._build_menu()
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

    def _setup_accessibility(self) -> None:
        self.progress.setAccessibleName("Transcription progress")
        self.status.setAccessibleName("Status")
        self.elapsed_label.setAccessibleName("Elapsed time")
        self.file_label.setAccessibleName("Selected file")
        self.output_preview.setAccessibleName("Output files")
        self.folder_button.setAccessibleName("Choose output folder")
        self.start_button.setAccessibleName("Create transcript")
        self.stop_button.setAccessibleName("Stop")
        self.log_view.setAccessibleName("Activity log")
        self.log_toggle.setAccessibleName("Toggle activity log")
        self.setTabOrder(self.folder_button, self.start_button)

    def _build_menu(self) -> None:
        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction("&About Taatik", self._show_about)
        help_menu.addAction("&Third-party notices", self._show_notices)

    def _show_about(self) -> None:
        QMessageBox.about(
            self, "About Taatik",
            f"<h3>Taatik {__version__}</h3>"
            "<p>Turn Hebrew audio or video into text and subtitles, entirely on "
            "your computer.</p>"
            "<p>Recordings and transcripts are never uploaded. Transcription uses "
            "whisper.cpp — GPU-accelerated on supported hardware — and FFmpeg.</p>"
            "<p>See <b>Help → Third-party notices</b> for licenses.</p>",
        )

    def _show_notices(self) -> None:
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
        notices = base / "THIRD_PARTY_NOTICES.md"
        try:
            text = notices.read_text(encoding="utf-8")
        except OSError:
            text = "Third-party notices file was not found in this build."
        dialog = QDialog(self)
        dialog.setWindowTitle("Third-party notices")
        dialog.resize(560, 480)
        browser = QTextBrowser(dialog)
        browser.setOpenExternalLinks(True)
        browser.setMarkdown(text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        box = QVBoxLayout(dialog)
        box.addWidget(browser)
        box.addWidget(buttons)
        dialog.exec()

    def _apply_theme(self) -> None:
        hints = QApplication.styleHints()
        scheme = hints.colorScheme() if hasattr(hints, "colorScheme") else Qt.ColorScheme.Light
        palette = _DARK if scheme == Qt.ColorScheme.Dark else _LIGHT
        self.setStyleSheet(_STYLESHEET.format(**palette))
        self.drop.set_accent(palette["accent"])

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
        self._update_output_preview()

    def _update_output_preview(self) -> None:
        if not self.source or not self.output_dir:
            self.output_preview.setText("")
            return
        try:
            base = unique_output_base(self.source, self.output_dir)
        except OSError:
            self.output_preview.setText("")
            return
        txt, srt = output_file(base, ".txt"), output_file(base, ".srt")
        self.output_preview.setText(f"Will save: {txt.name} and {srt.name}")

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
            self._update_output_preview()

    def start(self) -> None:
        if not self.source or not self.output_dir:
            return
        self.log_view.clear()
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
        separate = self.diar_check.isChecked()
        worker = TranscriptionWorker(
            self.source, self.output_dir, model_path(), bundled_tool("ffmpeg"), whisper_engines(),
            separate_speakers=separate,
            num_speakers=self.speaker_count.value(),
            diarization_models=diarization_models() if separate else None,
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
        if hasattr(worker, "log"):
            worker.log.connect(self._log)
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

    def _toggle_log(self) -> None:
        show = not self.log_view.isVisible()
        self.log_view.setVisible(show)
        self.log_toggle.setText("Hide log" if show else "Show log")
        self.settings.setValue("show_log", show)
        if show and self.isVisible():
            self.resize(self.width(), max(self.height(), 760))

    def _log(self, line: str) -> None:
        self.log_view.appendPlainText(line)

    def _busy(self, busy: bool) -> None:
        self.is_busy = busy
        self.start_button.setVisible(not busy)
        self.start_button.setEnabled(not busy and self.source is not None)
        self.stop_button.setVisible(busy)
        self.stop_button.setEnabled(busy)
        self.drop.setEnabled(not busy)
        self.folder_button.setEnabled(not busy)
        self.diar_check.setEnabled(not busy and diarization_ready())
        self.speaker_count.setEnabled(not busy and self.diar_check.isChecked())
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
