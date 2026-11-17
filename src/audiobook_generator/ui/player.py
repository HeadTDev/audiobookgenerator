"""Player bar: play/pause, clickable waveform seek bar, time and title."""
import math
import os
import shutil
import subprocess
from array import array

from PySide6.QtCore import QRectF, QSize, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

    HAS_MULTIMEDIA = True
except ImportError:
    HAS_MULTIMEDIA = False

from . import theme

PEAK_COUNT = 600  # waveform resolution; the widget resamples it to the bars that fit
DECODE_RATE = 800  # Hz: plenty for an amplitude envelope, keeps decoding fast
BAR_WIDTH = 3
BAR_GAP = 2


def format_time(ms):
    seconds = max(0, int(ms)) // 1000
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def compute_peaks(path, count=PEAK_COUNT):
    """Amplitude envelope of an audio file in 0..1, decoded with FFmpeg (mono, low rate)."""
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(DECODE_RATE), "-f", "s16le", "-"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    samples = array("h")
    samples.frombytes(result.stdout[: len(result.stdout) // 2 * 2])
    if not samples:
        return []
    step = max(1, len(samples) // count)
    # RMS (average loudness) rather than the peak: speech has a loud peak in almost every
    # bucket, so peaks would draw a flat block instead of sentences and pauses.
    levels = []
    for i in range(0, len(samples), step):
        bucket = samples[i:i + step]
        levels.append(math.sqrt(sum(s * s for s in bucket) / len(bucket)))
    # Stretch between a quiet floor and the loudest bucket so the shape is visible.
    floor = sorted(levels)[len(levels) // 10]
    span = (max(levels) - floor) or 1
    return [0.12 + 0.88 * min(1.0, max(0.0, (v - floor) / span)) for v in levels]


class WaveformLoader(QThread):
    loaded = Signal(str, list)

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self):
        try:
            peaks = compute_peaks(self.path)
        except (OSError, subprocess.CalledProcessError):
            peaks = []
        self.loaded.emit(self.path, peaks)


class WaveformSeekBar(QWidget):
    """Waveform that doubles as a seek bar: click or drag anywhere to jump there."""

    seek_requested = Signal(int)  # position in ms

    def __init__(self, parent=None):
        super().__init__(parent)
        self.peaks = []
        self.duration = 0
        self.position = 0
        self.hover_x = None
        self.setMinimumHeight(34)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self):
        return QSize(400, 34)

    def set_peaks(self, peaks):
        self.peaks = peaks
        self.update()

    def set_duration(self, duration):
        self.duration = max(0, duration)
        self.update()

    def set_position(self, position):
        self.position = position
        self.update()

    def reset(self):
        self.peaks, self.duration, self.position = [], 0, 0
        self.update()

    def _bar_heights(self, bar_count):
        if not self.peaks:
            return [0.12] * bar_count  # flat placeholder until the waveform is decoded
        per_bar = len(self.peaks) / bar_count
        return [
            max(self.peaks[int(i * per_bar): max(int(i * per_bar) + 1, int((i + 1) * per_bar))])
            for i in range(bar_count)
        ]

    def _ms_at(self, x):
        return int(min(max(x / max(1, self.width()), 0.0), 1.0) * self.duration)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        step = BAR_WIDTH + BAR_GAP
        bar_count = max(1, (self.width() + BAR_GAP) // step)
        mid = self.height() / 2
        usable = self.height() - 4

        enabled = self.isEnabled() and self.duration > 0
        played_x = self.position / self.duration * self.width() if enabled else -1
        hover_x = self.hover_x if enabled and self.hover_x is not None else None
        played = QColor(theme.ACCENT)
        preview = QColor(theme.ACCENT)
        preview.setAlphaF(0.45)
        idle = QColor("#3a3e47" if enabled else theme.BORDER)

        for i, level in enumerate(self._bar_heights(bar_count)):
            x = i * step
            height = max(3.0, level * usable)
            center = x + BAR_WIDTH / 2
            if center <= played_x:
                color = played
            elif hover_x is not None and played_x < center <= hover_x:
                color = preview
            else:
                color = idle
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(x, mid - height / 2, BAR_WIDTH, height), 1.5, 1.5)

        if hover_x is not None:
            painter.setBrush(QColor(theme.TEXT))
            painter.drawRect(QRectF(hover_x - 0.5, 2, 1, self.height() - 4))
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled() and self.duration:
            self._seek_to(event.position().x())

    def mouseMoveEvent(self, event):
        x = event.position().x()
        self.hover_x = x
        if self.isEnabled() and self.duration:
            if event.buttons() & Qt.MouseButton.LeftButton:
                self._seek_to(x)
            QToolTip.showText(event.globalPosition().toPoint(), format_time(self._ms_at(x)), self)
        self.update()

    def leaveEvent(self, event):
        self.hover_x = None
        QToolTip.hideText()
        self.update()

    def _seek_to(self, x):
        self.position = self._ms_at(x)
        self.seek_requested.emit(self.position)
        self.update()


class PlayerBar(QFrame):
    """Owns the media player. Use load() to play a file and release() to free it."""

    def __init__(self, parent=None):
        super().__init__(parent, objectName="playerBar")
        self.available = HAS_MULTIMEDIA
        self.current_path = None
        self.peak_cache = {}  # (path, mtime) -> peaks
        self.loader = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(14)

        self.play_btn = QPushButton(objectName="playButton")
        self.play_btn.setIcon(theme.play_icon())
        self.play_btn.setIconSize(QSize(14, 14))
        self.play_btn.setToolTip("Play / pause (Space)")
        self.play_btn.setEnabled(False)
        self.play_btn.clicked.connect(self.toggle)
        layout.addWidget(self.play_btn)

        column = QVBoxLayout()
        column.setSpacing(2)
        self.title_label = QLabel("Nothing playing", objectName="playerTitle")
        # Long titles are clipped instead of widening the window; full text is in the tooltip.
        self.title_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        column.addWidget(self.title_label)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.position_label = QLabel("00:00", objectName="timeLabel")
        self.wave = WaveformSeekBar()
        self.wave.setEnabled(False)
        self.duration_label = QLabel("00:00", objectName="timeLabel")
        row.addWidget(self.position_label)
        row.addWidget(self.wave, 1)
        row.addWidget(self.duration_label)
        column.addLayout(row)
        layout.addLayout(column, 1)

        if not self.available:
            return
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.playbackStateChanged.connect(self._on_state_changed)
        self.wave.seek_requested.connect(self.player.setPosition)

    def load(self, path, title):
        self.current_path = path
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.play()
        self.title_label.setText(title)
        self.title_label.setToolTip(path)
        self.play_btn.setEnabled(True)
        self.wave.setEnabled(True)
        self.wave.reset()
        self._load_waveform(path)

    def release(self):
        """Stop and unload, so Windows drops its lock on the file."""
        if not self.available:
            return
        self.player.stop()
        self.player.setSource(QUrl())
        self.current_path = None
        self.title_label.setText("Nothing playing")
        self.title_label.setToolTip("")
        self.play_btn.setEnabled(False)
        self.wave.setEnabled(False)
        self.wave.reset()
        self.position_label.setText("00:00")
        self.duration_label.setText("00:00")

    def shutdown(self):
        """Call on window close: stop playback and wait for a running waveform decode."""
        self.release()
        if self.loader and self.loader.isRunning():
            self.loader.wait()

    def toggle(self):
        if not self.available or self.player.source().isEmpty():
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _load_waveform(self, path):
        try:
            key = (path, os.path.getmtime(path))
        except OSError:
            return
        if key in self.peak_cache:
            self.wave.set_peaks(self.peak_cache[key])
            return
        if shutil.which("ffmpeg") is None:
            return
        self.loader = WaveformLoader(path, self)
        self.loader.loaded.connect(lambda _path, peaks, key=key: self._on_peaks(key, peaks))
        self.loader.start()

    def _on_peaks(self, key, peaks):
        self.peak_cache[key] = peaks
        if key[0] == self.current_path:  # ignore results for a file that is no longer loaded
            self.wave.set_peaks(peaks)

    def _on_position_changed(self, position):
        self.wave.set_position(position)
        self.position_label.setText(format_time(position))

    def _on_duration_changed(self, duration):
        self.wave.set_duration(duration)
        self.duration_label.setText(format_time(duration))

    def _on_state_changed(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.play_btn.setIcon(theme.pause_icon() if playing else theme.play_icon())
