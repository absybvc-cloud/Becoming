import subprocess
import threading
import sys
import os
from pathlib import Path


class Player:
    """Non-blocking audio player. Uses afplay on macOS, aplay on Linux, pydub as fallback."""

    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self.on_finish = None  # optional callback when playback ends

    def play(self, file_path: str):
        self.stop()
        if not Path(file_path).exists():
            print(f"[player] file not found: {file_path}")
            return
        self._thread = threading.Thread(target=self._play_worker, args=(file_path,), daemon=True)
        self._thread.start()

    def _play_worker(self, file_path: str):
        try:
            if sys.platform == "darwin":
                self._proc = subprocess.Popen(
                    ["afplay", file_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif sys.platform.startswith("linux"):
                self._proc = subprocess.Popen(
                    ["aplay", file_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                self._proc = None
                self._pydub_play(file_path)
                return

            self._proc.wait()
        except FileNotFoundError:
            # system player not found, fall back to pydub
            self._pydub_play(file_path)
        except Exception as e:
            print(f"[player] playback error: {e}")
        finally:
            self._proc = None
            if self.on_finish:
                self.on_finish()

    def _pydub_play(self, file_path: str):
        try:
            from pydub import AudioSegment
            from pydub.playback import play
            seg = AudioSegment.from_file(file_path)
            play(seg)
        except Exception as e:
            print(f"[player] pydub fallback failed: {e}")

    def stop(self):
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=2)
            except Exception:
                pass
        self._proc = None

    @property
    def is_playing(self) -> bool:
        return self._proc is not None and self._proc.poll() is None
