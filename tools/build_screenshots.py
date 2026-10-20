"""Gera as imagens do README (docs/media) abrindo o app de verdade, sem mostrar a janela.

Capturas em PNG na escala da tela (2x numa tela HiDPI) e animações em WebP (simulador,
linha do tempo, caixas automáticas, paleta de comandos, temas...). Usa o kfm de uma
instalação do MUGEN (arquivos oficiais da Elecbyte). Sem nomes de cena, gera todas.

    python tools/build_screenshots.py C:\\caminho\\do\\mugen [cena ...]
"""
from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "media"
SIZE = (1440, 860)          # janela, em pixels lógicos
MOTION_WIDTH = 1600         # largura das animações (as capturas ficam na escala da tela)


def pil(pixmap) -> Image.Image:
    from PySide6.QtCore import QBuffer, QIODevice
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")


def with_dialog(base: Image.Image, dialog: Image.Image, top: float | None = None) -> Image.Image:
    """Diálogo por cima da janela escurecida, com sombra."""
    out = Image.alpha_composite(base, Image.new("RGBA", base.size, (0, 0, 0, 110)))
    x = (base.width - dialog.width) // 2
    y = int(base.height * top) if top is not None else (base.height - dialog.height) // 2
    pad = 60
    shadow = Image.new("RGBA", (dialog.width + 2 * pad, dialog.height + 2 * pad), (0, 0, 0, 0))
    mask = Image.new("L", shadow.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((pad, pad + 12, pad + dialog.width, pad + dialog.height + 12),
                                           radius=24, fill=150)
    shadow.putalpha(mask.filter(ImageFilter.GaussianBlur(28)))
    out.alpha_composite(shadow, (x - pad, y - pad))
    out.alpha_composite(dialog, (x, y))
    return out


def save_png(img: Image.Image, name: str) -> None:
    img.convert("RGB").save(OUT / name, optimize=True)
    print(f"{name}: {img.width}x{img.height}, {(OUT / name).stat().st_size // 1024} KB")


def save_motion(frames: list[Image.Image], durations: list[int], name: str) -> None:
    w = MOTION_WIDTH
    small = [f.convert("RGB").resize((w, round(f.height * w / f.width)), Image.Resampling.LANCZOS)
             for f in frames]
    small[0].save(OUT / name, save_all=True, append_images=small[1:], duration=durations, loop=0,
                  quality=90, method=6)
    print(f"{name}: {len(frames)} frames, {(OUT / name).stat().st_size // 1024} KB")


def font(names: list[str], size: int):
    from PIL import ImageFont
    dirs = [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts", ROOT / "charfactory" / "gui" / "fonts"]
    for name in names:
        for d in dirs:
            if (d / name).exists():
                return ImageFont.truetype(str(d / name), size)
    return ImageFont.load_default(size)


def rounded(img: Image.Image, radius: int) -> Image.Image:
    img = img.convert("RGBA")
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.width - 1, img.height - 1), radius=radius, fill=255)
    img.putalpha(mask)
    return img


def banner(screen: Image.Image, ui: dict) -> Image.Image:
    """Capa 2560x1280 (reduzida a 1280x640 vira a prévia social do GitHub): ícone, nome, frase e a janela."""
    def rgb(h: str) -> tuple[int, int, int]:
        return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))
    W, H, S = 1280, 640, 2                      # desenha em 2x e reduz no fim
    bg, accent, text, dim = rgb(ui["window"]), rgb(ui["accent"]), rgb(ui["text"]), rgb(ui["text_dim"])
    img = Image.new("RGBA", (W * S, H * S), bg + (255,))
    # brilho verde suave atrás da janela
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((W * S * 0.45, H * S * 0.05, W * S * 1.25, H * S * 1.2), fill=accent + (80,))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(160)))
    # grade de pontos discreta, como o canvas do app
    dots = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(dots)
    for x in range(0, W * S, 48):
        fade = min(1.0, max(0.0, (x - W * S * 0.38) / (W * S * 0.12)))   # some atrás do texto
        for y in range(0, H * S, 48):
            if fade:
                d.ellipse((x - 2, y - 2, x + 2, y + 2), fill=text + (int(40 * fade),))
    img.alpha_composite(dots)
    # janela do app à direita, cortada pela borda
    w = int(W * S * 0.62)
    win = rounded(screen.resize((w, round(screen.height * w / screen.width)), Image.Resampling.LANCZOS), 28)
    x, y = int(W * S * 0.47), int(H * S * 0.16)
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((x, y + 30, x + win.width, y + win.height + 30), radius=28,
                                             fill=(0, 0, 0, 170))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(40)))
    img.alpha_composite(win, (x, y))
    edge = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(edge).rounded_rectangle((x, y, x + win.width - 1, y + win.height - 1), radius=28,
                                           outline=text + (50,), width=3)
    img.alpha_composite(edge)
    # texto à esquerda
    d = ImageDraw.Draw(img)
    icon = Image.open(ROOT / "charfactory" / "gui" / "assets" / "charfactory.png").convert("RGBA")
    icon = icon.resize((150, 150), Image.Resampling.LANCZOS)
    left = 110
    img.alpha_composite(icon, (left, 250))
    d.text((left, 450), "Char Factory", font=font(["segoeuib.ttf", "JetBrainsMono-Bold.ttf"], 128), fill=text)
    d.text((left + 4, 620), "M.U.G.E.N character editor", font=font(["seguisb.ttf", "JetBrainsMono-Medium.ttf"], 52),
           fill=accent)
    small = font(["segoeui.ttf", "JetBrainsMono-Regular.ttf"], 38)
    for i, line in enumerate(["Sprites, animations, Clsn boxes, sounds and code,",
                              "plus a tick-by-tick move simulator.", "Free and open source."]):
        d.text((left + 4, 730 + i * 54), line, font=small, fill=dim)
    chips, cx = ["SFF v1/v2", "AIR", "CNS", "CMD", "ZSS"], left
    chip_font = font(["seguisb.ttf", "JetBrainsMono-Medium.ttf"], 32)
    for c in chips:
        tw = d.textlength(c, font=chip_font)
        d.rounded_rectangle((cx, 940, cx + tw + 44, 1000), radius=30, fill=rgb(ui["accent_soft"]),
                            outline=rgb(ui["accent_soft"]), width=2)
        d.text((cx + 22 + tw / 2, 970), c, font=chip_font, fill=accent, anchor="mm")
        cx += tw + 60
    return img


def caption(img: Image.Image, text: str) -> Image.Image:
    """Legenda em pílula no alto do quadro (abaixo da barra de ferramentas)."""
    img = img.copy()
    s = img.width / 2880
    f = font(["seguisb.ttf", "JetBrainsMono-Medium.ttf"], round(44 * s))
    d = ImageDraw.Draw(img)
    tw = d.textlength(text, font=f)
    pad_x, h = round(36 * s), round(84 * s)
    x0 = (img.width - tw) / 2 - pad_x
    y0 = round(250 * s)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle((x0, y0, x0 + tw + 2 * pad_x, y0 + h), radius=h // 2,
                                            fill=(12, 12, 10, 225))
    img.alpha_composite(layer)
    ImageDraw.Draw(img).text((img.width / 2, y0 + h / 2), text, font=f, fill=(248, 248, 242), anchor="mm")
    return img


def pointer(img: Image.Image, x: float, y: float) -> Image.Image:
    """Seta do mouse desenhada em (x, y), já que a captura não inclui o cursor."""
    img = img.copy()
    k = img.width / 2880 * 2.2
    pts = [(0, 0), (0, 17), (4.5, 13), (7.5, 20), (10, 19), (7, 12.5), (12.5, 12.5)]
    poly = [(x + px * k, y + py * k) for px, py in pts]
    d = ImageDraw.Draw(img)
    d.polygon(poly, fill=(255, 255, 255), outline=(0, 0, 0), width=max(2, round(k)))
    return img


def card(dialog: Image.Image, ui: dict) -> Image.Image:
    """Diálogo sozinho sobre um fundo da cor do tema, com sombra (para as imagens em grade)."""
    pad = 70
    bg = tuple(int(ui["window"][i:i + 2], 16) for i in (1, 3, 5))
    accent = tuple(int(ui["accent"][i:i + 2], 16) for i in (1, 3, 5))
    out = Image.new("RGBA", (dialog.width + 2 * pad, dialog.height + 2 * pad), bg + (255,))
    glow = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((out.width * 0.2, out.height * 0.3, out.width * 1.1, out.height * 1.3),
                                 fill=accent + (40,))
    out.alpha_composite(glow.filter(ImageFilter.GaussianBlur(120)))
    shadow = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((pad, pad + 16, pad + dialog.width, pad + dialog.height + 16),
                                             radius=20, fill=(0, 0, 0, 160))
    out.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(26)))
    out.alpha_composite(rounded(dialog, 14), (pad, pad))
    return out


def terminal(blocks: list[tuple[str, str]], ui: dict) -> Image.Image:
    """Janela de terminal com comandos e a saída real deles."""
    def rgb(h: str) -> tuple[int, int, int]:
        return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))
    f = font(["JetBrainsMono-Regular.ttf"], 30)
    fb = font(["JetBrainsMono-Bold.ttf"], 30)
    lines: list[tuple[str, tuple, object]] = []
    for cmd, output in blocks:
        lines.append(("> " + cmd, rgb(ui["accent"]), fb))
        lines += [(ln, rgb(ui["text"]), f) for ln in output.rstrip().splitlines()]
        lines.append(("", rgb(ui["text"]), f))
    lines.pop()
    lh, pad, bar = 44, 48, 76
    width = 1900
    height = bar + pad * 2 + lh * len(lines)
    win = Image.new("RGBA", (width, height), rgb(ui["panel"]) + (255,))
    d = ImageDraw.Draw(win)
    d.rectangle((0, 0, width, bar), fill=rgb(ui["window"]))
    for i, c in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        d.ellipse((32 + i * 40, bar / 2 - 11, 54 + i * 40, bar / 2 + 11), fill=c)
    d.text((width / 2, bar / 2), "PowerShell", font=f, fill=rgb(ui["text_dim"]), anchor="mm")
    for i, (text, color, fnt) in enumerate(lines):
        d.text((pad, bar + pad + i * lh), text, font=fnt, fill=color)
    return card(win, ui)


def main() -> int:
    if len(sys.argv) < 2 or not (Path(sys.argv[1]) / "chars" / "kfm" / "kfm.def").exists():
        print("usage: python tools/build_screenshots.py <MUGEN folder with chars/kfm> [scene ...]")
        return 1
    mugen = Path(sys.argv[1])
    wanted = set(sys.argv[2:])
    tmp = Path(tempfile.mkdtemp(prefix="charfactory-shots-"))
    os.environ["APPDATA"] = str(tmp / "appdata")          # configuração limpa, sem a do usuário
    os.environ["CHARFACTORY_LANG"] = "en"
    shutil.copytree(mugen / "chars" / "kfm", tmp / "chars" / "kfm")
    shutil.copytree(mugen / "chars" / "kfm", tmp / "chars" / "kfm2")   # origem do transplante
    (tmp / "data").mkdir()
    shutil.copy(mugen / "data" / "common1.cns", tmp / "data")
    OUT.mkdir(parents=True, exist_ok=True)

    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication([])
    from charfactory.gui.app import APP_NAME, MainWindow, app_icon, install_translator
    from charfactory.gui.context import AppContext
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(app_icon())
    install_translator(app)
    ctx = AppContext()
    win = MainWindow(ctx)
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    win.resize(*SIZE)
    win.show()
    # avisos modais travariam a captura
    QMessageBox.information = QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)

    def settle(n: int = 8) -> None:
        for _ in range(n):
            app.processEvents()
            time.sleep(0.01)

    def wait(cond, timeout: float = 120) -> bool:
        t = time.perf_counter()
        while not cond() and time.perf_counter() - t < timeout:
            settle(1)
        return cond()

    def shot() -> Image.Image:
        settle()
        return pil(win.grab())

    def at(widget, x: float, y: float) -> tuple[float, float]:
        """Ponto do widget em pixels da captura da janela."""
        p = widget.mapTo(win, QPoint(round(x), round(y)))
        dpr = win.devicePixelRatioF()
        return p.x() * dpr, p.y() * dpr

    def on_exec(cls, fn) -> None:
        """Troca o exec() do diálogo por: mostrar, rodar fn(dlg) (que captura) e fechar."""
        def run(dlg, *_):
            dlg.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
            dlg.show()
            settle(12)
            fn(dlg)
            dlg.reject()
            return 0
        cls.exec = run

    def grab(widget) -> Image.Image:
        settle(12)
        return pil(widget.grab())

    settle()
    win.open_path(str(tmp / "chars" / "kfm" / "kfm.def"))
    settle()
    an, sp = win.anims, win.simulator
    an.onion.setChecked(False)
    ui = ctx.theme.ui

    def pose(frame: int, action: int = 210) -> None:
        win.show_page(an)
        an.select_action(action)
        settle()
        an.group_combo.setCurrentIndex(max(0, an.group_combo.findData(action)))
        an.canvas.set_zoom(4)
        an.frame_nav.set_index(frame)

    def simulate(state: int) -> bool:
        win.show_page(sp)
        sp.run_state(state)
        settle(4)
        return wait(lambda: sp.sim is not None)

    def tick_frames(duration: int = 60) -> tuple[list[Image.Image], list[int]]:
        frames, durations = [], []
        for tick in range(sp.slider.maximum() + 1):
            sp.slider.setValue(tick)
            wait(lambda: not sp._rendering and sp._key(tick) in sp.cache, 20)
            frames.append(shot())
            durations.append(duration)
        durations[-1] = 1200
        return frames, durations

    # ------------------------------------------------------------------ destaques

    def s_animations():
        pose(4)
        hero = shot()
        save_png(hero, "animations.png")
        cover = banner(hero, ui)
        save_png(cover, "banner.png")
        save_png(cover.resize((1280, 640), Image.Resampling.LANCZOS), "social-preview.png")
        pose(0)
        frames, durations = [], []
        for i, fr in enumerate(ctx.char.anims.get(210).frames):   # meia velocidade
            an.frame_nav.set_index(i)
            frames.append(shot())
            durations.append(max(1, fr.time if fr.time > 0 else 30) * 33)
        durations[-1] += 600
        save_motion(frames, durations, "animation.webp")

    def s_editors():
        win.show_page(win.sprites)
        win.sprites.select(5000, 0)
        win.sprites.canvas.set_zoom(4)
        save_png(shot(), "sprites.png")
        win.goto_code("kfm.cns", "[Statedef 210]")
        save_png(shot(), "code.png")
        win.show_page(win.sounds)
        win.sounds.select(5, 0)
        save_png(shot(), "sounds.png")

    def s_image_editor():
        from charfactory.gui import imageeditor
        win.show_page(win.sprites)
        win.sprites.select(0, 0)
        settle()
        base = shot()
        stills, frames = [], []

        def run(dlg):
            stills.append(grab(dlg))
            for _ in range(6):                     # PgDn: os quadros da pose parada, um a um
                frames.append(card(grab(dlg), ui))
                dlg.go(1)
        on_exec(imageeditor.ImageEditor, run)
        win.sprites.edit_image()
        save_png(with_dialog(base, stills[0]), "image-editor.png")
        save_motion(frames, [260] * len(frames), "only-pixel-editor.webp")

    def s_command_palette():
        from charfactory.gui import dialogs
        win.show_page(an)
        base = shot()
        frames, durations = [], []

        def run(dlg):
            dlg.edit.setText("anim")
            save_png(with_dialog(base, grab(dlg), top=0.08), "command-palette.png")
            dlg.edit.setText("")
            for k in range(len("state 1000") + 1):
                dlg.edit.setText("state 1000"[:k])
                frames.append(with_dialog(base, grab(dlg), top=0.08))
                durations.append(110)
            durations[-1] = 900
            dlg.run(dlg.list.item(0))              # Enter: abre o estado no código
        on_exec(dialogs.CommandPalette, run)
        win.command_palette()
        frames.append(caption(shot(), "Enter jumps to [Statedef 1000]"))
        durations.append(2600)
        save_motion(frames, durations, "only-command-palette.webp")

    def s_simulator():
        if not simulate(210):
            raise RuntimeError("the simulation did not finish")
        frames, durations = tick_frames()
        save_png(frames[min(len(frames) - 1, 8)], "simulator.png")
        save_motion(frames, durations, "simulator.webp")

    def s_themes():
        pose(4)
        frames, names = [], list(ctx.themes)
        for name in names:
            ctx.set_theme(name)
            frames.append(shot())
        ctx.set_theme(names[0])
        save_motion(frames, [1400] * len(frames), "themes.webp")

    # ------------------------------------------------------------------ só no Char Factory

    def s_compare():
        """A/B com um backup: a versão atual tem uma pausa de acerto maior."""
        win.create_backup()
        win.flash("Backup created")               # a mensagem padrão mostra a pasta temporária
        hit = next(c for c in ctx.char.all_statedefs()[210][0].controllers if c.type.lower() == "hitdef")
        old = hit.section.get("pausetime")
        hit.section.set("pausetime", "24, 24")
        ctx.changed("states")
        win.show_page(sp)
        sp.compare.setCurrentIndex(2)
        ok = simulate(210)
        frames, durations = tick_frames(50) if ok else ([], [])
        hit.section.set("pausetime", old)
        ctx.changed("states")
        sp.compare.setCurrentIndex(0)
        if frames:
            save_motion(frames, durations, "only-compare.webp")

    def s_timeline():
        """Arrastar o PlaySnd na linha do tempo reescreve o Time = N; duplo clique abre o código."""
        if not simulate(200):
            raise RuntimeError("the simulation did not finish")
        tl = sp.timeline
        y = tl.RULER_H + [k for k, _ in tl.rows_def].index("sons") * tl.ROW_H + tl.ROW_H // 2

        def sound():
            return next(it for it in tl.data["rows"]["sons"] if not it.get("hitsound"))
        start = sound()["i0"]

        def trigger() -> str:
            ctrl, _ = sp._controller(sound())
            return " ".join(ctrl.section.get("trigger1").split())
        before = trigger()
        x0, x1 = tl._x(start) + 3, tl._x(start + 5) + 3
        first = shot()
        frames = [caption(pointer(first, *at(tl, x0, y)), "Drag the PlaySnd to another tick")]
        durations = [1300]
        QTest.mousePress(tl, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(round(x0), y))
        steps = 10
        for k in range(1, steps + 1):
            x = x0 + (x1 - x0) * k / steps
            QTest.mouseMove(tl, QPoint(round(x), y))
            frames.append(caption(pointer(shot(), *at(tl, x, y)), "Drag the PlaySnd to another tick"))
            durations.append(70)
        old = sp.sim
        QTest.mouseRelease(tl, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(round(x1), y))
        wait(lambda: sp.sim is not None and sp.sim is not old)
        x = tl._x(sound()["i0"]) + 3
        frames.append(caption(pointer(shot(), *at(tl, x, y)), f"{before}  →  {trigger()}"))
        durations.append(1800)
        QTest.mouseClick(tl, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(round(x), y))
        QTest.mouseDClick(tl, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(round(x), y))
        settle(20)
        frames.append(caption(shot(), "Double-click opens the controller in the code"))
        durations.append(2800)
        save_motion(frames, durations, "only-timeline.webp")
        ctx.undo()

    def s_clsn():
        """Quadro sem caixas, Clsn2 anatômica e Clsn1 de ataque automáticas."""
        pose(4)
        f = an.frame()
        saved = (f.clsn1, f.clsn2)
        f.clsn1, f.clsn2 = [], []
        an.show_frame()
        frames = [caption(shot(), "A frame without boxes")]
        an.auto_box_anatomical()
        frames.append(caption(shot(), "Anatomical Clsn2 from the silhouette"))
        an.auto_box_attack()
        frames.append(caption(shot(), "Attack Clsn1 on the extended arm"))
        save_motion(frames, [1300, 1700, 2600], "only-clsn.webp")
        f.clsn1, f.clsn2 = saved
        an.show_frame()

    def s_tools():
        from charfactory.gui import dialogs
        from charfactory.gui import dialogs_tools
        from charfactory.gui import movewizard
        from charfactory.gui import palettes12
        from charfactory.tools import charkit

        def transplant(dlg):
            src = str(tmp / "chars" / "kfm2" / "kfm.def")
            dlg.path.setText(src)
            dlg.load_src(src)
            dlg.state.setCurrentIndex(max(0, dlg.state.findData(1000)))
            dlg.suggest()
            dlg.path.setText(r"chars\kfm2\kfm.def")   # sem a pasta temporária na imagem
            save_png(card(grab(dlg), ui), "only-transplant.png")
        on_exec(dialogs_tools.TransplantDialog, transplant)
        win.transplant_move()

        on_exec(movewizard.MoveWizardDialog, lambda dlg: save_png(card(grab(dlg), ui), "only-move-wizard.png"))
        win.move_wizard(210)

        # folha de sprites montada com a caminhada do kfm, para o recorte achar os quadros
        sprites = [charkit.sprite_rgba(ctx.char, 20, i)[0] for i in range(0, 16, 2)]
        w = sum(s.width for s in sprites) + 24 * (len(sprites) + 1)
        h = max(s.height for s in sprites) + 48
        sheet = Image.new("RGB", (w, h), (61, 122, 116))
        x = 24
        for s in sprites:
            sheet.paste(s, (x, h - 24 - s.height), s)
            x += s.width + 24
        sheet_path = tmp / "walk-sheet.png"
        sheet.save(sheet_path)

        def slicer(dlg):
            dlg.path.setText(str(sheet_path))
            dlg.run_preview()
            dlg.path.setText("walk-sheet.png")
            save_png(card(grab(dlg), ui), "only-sheet.png")
        on_exec(dialogs.SheetDialog, slicer)
        win.sheet()

        on_exec(palettes12.PaletteSetDialog, lambda dlg: save_png(card(grab(dlg), ui), "only-palettes12.png"))
        win.show_page(win.sprites)
        win.sprites.open_palettes12()

        on_exec(dialogs.UnusedDialog, lambda dlg: save_png(card(grab(dlg), ui), "only-unused.png"))
        win.unused_resources()

    def s_cli():
        import subprocess
        kfm = tmp / "chars" / "kfm" / "kfm.def"
        env = dict(os.environ, CHARFACTORY_LANG="en", PYTHONIOENCODING="utf-8")
        blocks = []
        for args in (["info", str(kfm)], ["validate", str(kfm)]):
            r = subprocess.run([sys.executable, "-m", "charfactory.cli", *args], capture_output=True,
                               text=True, encoding="utf-8", env=env, cwd=ROOT)
            out = r.stdout + r.stderr
            if args[0] == "info":                 # sem o caminho da pasta e com os estados resumidos
                import json
                data = json.loads(out)
                states = data.get("statedefs", [])
                data["statedefs"] = f"{len(states)} states: {', '.join(map(str, states[:6]))}, …"
                out = json.dumps({k: data[k] for k in ("name", "author", "mugenversion", "sprites",
                                                        "animations", "sounds", "commands", "statedefs")
                                  if k in data}, indent=1, ensure_ascii=False)
            out = out.replace(str(kfm.parent) + os.sep, "").replace(str(tmp), "…")
            lines = [ln if len(ln) <= 96 else ln[:95] + "…" for ln in out.splitlines()]
            blocks.append((f"charfactory {args[0]} kfm.def", "\n".join(lines)))
        save_png(terminal(blocks, ui), "only-cli.png")

    scenes = {"animations": s_animations, "editors": s_editors, "image-editor": s_image_editor,
              "command-palette": s_command_palette, "simulator": s_simulator, "themes": s_themes,
              "compare": s_compare, "timeline": s_timeline, "clsn": s_clsn, "tools": s_tools, "cli": s_cli}
    for name, fn in scenes.items():
        if not wanted or name in wanted:
            fn()

    win.close()
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
