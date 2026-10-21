"""Ponto de entrada da interface: escolhe o idioma (na primeira abertura, com a telinha de idioma
e tema) antes de importar a janela principal, cujos rótulos são traduzidos ao importar."""
from __future__ import annotations

import sys


def restart_command() -> tuple[str, list[str]]:
    """Programa e argumentos para abrir o app de novo (o .exe empacotado ou o Python)."""
    if getattr(sys, "frozen", False):
        return sys.executable, []
    return sys.executable, ["-m", "charfactory.gui"]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    if "--mcp" in argv:
        # servidor MCP em stdio sem abrir a janela (clientes que só falam stdio, como o Claude
        # Desktop, chamam o executável assim); o .exe é --windowed: sem os canais do cliente
        # não há stdin/stdout
        if sys.stdin is None or sys.stdout is None:
            return 1
        from ..ai import mcp
        rest = [a for a in argv[1:] if a != "--mcp"]
        return mcp.main_stdio(next((a for a in rest if not a.startswith("--")), None), "--standalone" in rest)
    if sys.platform == "win32":
        # identidade própria na barra de tarefas (sem isso o Windows agrupa sob o python.exe)
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CharFactory.App")
        except (AttributeError, OSError):
            pass
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(argv)
    from . import firstrun
    if firstrun.needed():
        firstrun.run()
    from .app import run
    return run(app, argv)


if __name__ == "__main__":
    sys.exit(main())
