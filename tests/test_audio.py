"""Reprodução de WAV (gui/audio.py): um som por vez, loop opcional; afplay no macOS."""
import sys
import time
import wave

import pytest

from charfactory.gui import audio


def _wav(tmp_path) -> str:
    p = tmp_path / "t.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 8000)   # 1 s de silêncio
    return str(p)


def test_stop_without_playing_is_safe():
    audio.Player().stop()


@pytest.mark.skipif(sys.platform != "darwin", reason="afplay é do macOS")
def test_play_and_stop_a_wav(tmp_path):
    p = audio.Player()
    p.play(_wav(tmp_path))
    time.sleep(0.3)          # sem saída de áudio (CI) o afplay termina: o watcher cuida
    p.stop()                 # não pode quebrar, com ou sem som tocando
    time.sleep(0.1)
    assert p._proc is None or p._proc.poll() is not None
