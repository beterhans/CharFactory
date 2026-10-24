"""Gera o executável do Char Factory com o PyInstaller.

    python tools/build_exe.py            # Windows: dist/Char Factory/Char Factory.exe
                                         # macOS:   dist/Char Factory.app
    python tools/build_exe.py dist/novo  # outra pasta (o exe antigo aberto trava a pasta padrão)

Precisa do PyInstaller no mesmo Python do projeto (pip install pyinstaller). O ícone vem de
charfactory/gui/assets/charfactory.ico no Windows e charfactory.icns no macOS (tools/build_app_icon.py).
As ferramentas do charfactory são importadas sob demanda, então todos os submódulos e arquivos de
dados do pacote vão junto. No macOS o bundle sai sem assinatura: na primeira abertura, clique com
o botão direito e escolha "Abrir" (Gatekeeper).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "Char Factory"
IS_MAC = sys.platform == "darwin"
# módulos do Qt que o app não usa (deixam a pasta bem menor)
EXCLUDE = ["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
           "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtQuick", "PySide6.QtQml",
           "PySide6.QtQuick3D", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtPdf",
           "PySide6.QtMultimedia", "PySide6.QtBluetooth", "PySide6.QtSensors", "PySide6.QtSerialPort",
           "tkinter", "matplotlib", "pytest"]


def main() -> int:
    import PyInstaller.__main__
    dist = (ROOT / sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist"
    work = ROOT / "build" / "pyinstaller"
    entry = work / "charfactory_gui_main.py"
    work.mkdir(parents=True, exist_ok=True)
    entry.write_text("from charfactory.gui.launch import main\nraise SystemExit(main())\n", "utf-8")
    icon = ROOT / "charfactory" / "gui" / "assets" / ("charfactory.icns" if IS_MAC else "charfactory.ico")
    args = [str(entry), "--name", NAME, "--windowed", "--noconfirm", "--clean",
            "--icon", str(icon),
            "--paths", str(ROOT),
            "--collect-submodules", "charfactory", "--collect-data", "charfactory",
            "--distpath", str(dist), "--workpath", str(work), "--specpath", str(work)]
    if IS_MAC:
        args += ["--osx-bundle-identifier", "com.charfactory.app"]
    for m in EXCLUDE:
        args += ["--exclude-module", m]
    PyInstaller.__main__.run(args)
    out = dist / (f"{NAME}.app" if IS_MAC else f"{NAME}/{NAME}.exe")
    print("executable:", out if out.exists() else "not built")
    return 0 if out.exists() else 1


if __name__ == "__main__":
    sys.exit(main())
