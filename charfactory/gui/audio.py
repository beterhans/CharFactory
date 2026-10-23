"""Toca um WAV de forma assíncrona, um som por vez: winsound no Windows e afplay nos
demais sistemas (macOS). play() para o que estiver tocando, como o winsound fazia."""
from __future__ import annotations

import os
import subprocess
import threading


class Player:
    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self._loop = False
        self._gen = 0

    def play(self, path: str, loop: bool = False) -> None:
        self.stop()
        if os.name == "nt":
            import winsound
            flags = winsound.SND_FILENAME | winsound.SND_ASYNC | (winsound.SND_LOOP if loop else 0)
            winsound.PlaySound(path, flags)
            return
        self._gen += 1
        gen = self._gen
        self._loop = loop
        self._proc = subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        threading.Thread(target=self._watch, args=(path, gen), daemon=True).start()

    def _watch(self, path: str, gen: int) -> None:
        # loop: quando o afplay termina, toca de novo (enquanto não for parado)
        while self._loop and gen == self._gen:
            proc = self._proc
            if proc is None or proc.wait() != 0:
                return
            if not (self._loop and gen == self._gen):      # parado enquanto o som terminava
                return
            self._proc = subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def stop(self) -> None:
        self._loop = False
        self._gen += 1
        if os.name == "nt":
            try:
                import winsound
                winsound.PlaySound(None, 0)
            except ImportError:
                pass
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
        self._proc = None


player = Player()   # um por vez, como o winsound
