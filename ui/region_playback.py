"""Play a decoded selection as its own bounded media source."""

import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from converter.regions import export_region


class RegionPlayback(QObject):
    position_changed = Signal(float)
    state_changed = Signal(object)
    ready = Signal()
    error = Signal(str)
    prepared = Signal(object, object, object)
    ended = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="selection-playback")
        self.folder = tempfile.TemporaryDirectory(prefix="audiobridge-listen-")
        self.token = None
        self.region = None
        self.clip = None
        self.closed = False
        self.futures = set()
        self.prepared.connect(self._prepared)
        self.player.positionChanged.connect(self._position)
        self.player.playbackStateChanged.connect(lambda state: self.state_changed.emit(state))
        self.player.mediaStatusChanged.connect(self._status)
        self.player.errorOccurred.connect(lambda error, message: self.error.emit(message))

    @property
    def active(self):
        return self.token is not None

    def play(self, source, region):
        self.stop()
        self.region = region
        token = self.token = uuid.uuid4().hex
        destination = Path(self.folder.name) / (token + ".wav")
        future = self.pool.submit(export_region, source, destination, region, bit_depth=24)
        self.futures.add(future)

        def finished(result):
            self.futures.discard(result)
            if result.cancelled():
                if self.closed and not self.futures:
                    self.folder.cleanup()
                return
            try:
                path, error = result.result(), None
            except Exception as exc:
                path, error = None, str(exc)
            if self.closed:
                if path:
                    path.unlink(missing_ok=True)
                if not self.futures:
                    self.folder.cleanup()
                return
            self.prepared.emit(token, path, error)

        future.add_done_callback(finished)

    def _prepared(self, token, path, error):
        if self.closed or token != self.token:
            if path:
                path.unlink(missing_ok=True)
            return
        if error:
            self.token = None
            self.error.emit(error)
            return
        self.clip = path
        self.player.setSource(QUrl.fromLocalFile(str(path)))

    def _status(self, status):
        if status == QMediaPlayer.MediaStatus.LoadedMedia and self.active:
            self.ready.emit()
            self.player.play()
        elif status == QMediaPlayer.MediaStatus.EndOfMedia and self.region:
            end = self.region.end
            self.stop()
            self.ended.emit(end)

    def _position(self, position):
        if self.region:
            self.position_changed.emit(self.region.start * 1000 + position)

    def toggle(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        elif self.clip:
            self.player.play()

    def stop(self):
        if self.token is None and self.region is None and self.clip is None:
            return
        self.token = None
        self.player.stop()
        self.player.setSource(QUrl())
        self.region = None
        if self.clip:
            self.clip.unlink(missing_ok=True)
            self.clip = None

    def close(self):
        self.stop()
        self.closed = True
        self.pool.shutdown(wait=False, cancel_futures=True)
        if not self.futures:
            self.folder.cleanup()
