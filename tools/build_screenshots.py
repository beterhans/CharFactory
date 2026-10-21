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

# o golpe que o assistente cria na animação do README: pula chutando e emenda um combo que
# lança o oponente (testado no simulador do kfm: 4 acertos)
AI_AIR_STATE = """[Statedef 1500]
type = A
movetype = A
physics = A
anim = 1500
ctrl = 0
velset = 3.5, -6
poweradd = 40
juggle = 2
facep2 = 1
sprpriority = 2

[State 1500, flying kick]
type = HitDef
trigger1 = AnimElem = 2
attr = A, SA
damage = 40, 5
animtype = Medium
guardflag = HA
hitflag = MAF
pausetime = 8, 10
sparkxy = -10, -60
hitsound = S5, 2
guardsound = S6, 0
ground.type = High
ground.slidetime = 6
ground.hittime = 24
ground.velocity = -1
air.velocity = -1, -2

[State 1500, land into the combo]
type = ChangeState
trigger1 = vel y > 0 && pos y + vel y >= 0
value = 1501
"""

AI_COMBO_STATE = """[Statedef 1501]
type = S
movetype = A
physics = S
anim = 1501
ctrl = 0
velset = 1, 0
sprpriority = 2

[State 1501, on the ground]
type = PosSet
trigger1 = Time = 0
y = 0

[State 1501, punch]
type = HitDef
trigger1 = AnimElem = 2
attr = S, SA
damage = 25, 3
animtype = Light
guardflag = MA
pausetime = 6, 8
sparkxy = -10, -76
hitsound = S5, 0
guardsound = S6, 0
ground.type = High
ground.slidetime = 6
ground.hittime = 18
ground.velocity = -1

[State 1501, strong punch]
type = HitDef
trigger1 = AnimElem = 4
attr = S, SA
damage = 35, 4
animtype = Medium
guardflag = MA
pausetime = 8, 10
sparkxy = -10, -76
hitsound = S5, 2
guardsound = S6, 0
ground.type = High
ground.slidetime = 8
ground.hittime = 20
ground.velocity = -1.5

[State 1501, launcher kick]
type = HitDef
trigger1 = AnimElem = 6
attr = S, SA
damage = 70, 8
animtype = Hard
guardflag = MA
pausetime = 14, 16
sparkno = 3
sparkxy = -10, -70
hitsound = S5, 4
guardsound = S6, 0
ground.type = High
ground.velocity = -10, -6
air.velocity = -10, -6
fall = 1
fall.recover = 0

[State 1501, back to stand]
type = ChangeState
trigger1 = AnimTime = 0
value = 0
ctrl = 1
"""

AI_JUMP_KICK = [{"group": 640, "item": 0, "time": 6}, {"group": 640, "item": 1, "time": 40, "attack": True},
             {"group": 640, "item": 2, "time": -1}]
AI_COMBO = [{"group": 200, "item": 1, "time": 2}, {"group": 200, "item": 2, "time": 4, "attack": True},
         {"group": 210, "item": 2, "time": 3}, {"group": 210, "item": 3, "time": 4, "attack": True},
         {"group": 240, "item": 1, "time": 3}, {"group": 240, "item": 2, "time": 5, "attack": True},
         {"group": 240, "item": 4, "time": 5}, {"group": 240, "item": 5, "time": 4},
         {"group": 200, "item": 0, "time": 4}]


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
                              "a tick-by-tick move simulator and AI agents",
                              "(Claude, Codex, Gemini) that edit through MCP."]):
        d.text((left + 4, 730 + i * 54), line, font=small, fill=dim)
    chips, cx = ["AI + MCP", "SFF v1/v2", "AIR", "CNS", "ZSS"], left
    chip_font = font(["seguisb.ttf", "JetBrainsMono-Medium.ttf"], 32)
    for k, c in enumerate(chips):               # o primeiro, a IA, cheio na cor de destaque
        tw = d.textlength(c, font=chip_font)
        d.rounded_rectangle((cx, 940, cx + tw + 44, 1000), radius=30,
                            fill=accent if k == 0 else rgb(ui["accent_soft"]), outline=rgb(ui["accent_soft"]), width=2)
        d.text((cx + 22 + tw / 2, 970), c, font=chip_font, fill=rgb(ui["accent_text"]) if k == 0 else accent,
               anchor="mm")
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


GRID_ASPECT = 16 / 10       # imagens lado a lado no README: mesma proporção, textos alinhados


def card(dialog: Image.Image, ui: dict, aspect: float | None = None) -> Image.Image:
    """Diálogo sozinho sobre um fundo da cor do tema, com sombra (para as imagens em grade).
    Com `aspect`, o fundo cresce até essa proporção (largura/altura) com o diálogo no centro."""
    pad = 70
    bg = tuple(int(ui["window"][i:i + 2], 16) for i in (1, 3, 5))
    accent = tuple(int(ui["accent"][i:i + 2], 16) for i in (1, 3, 5))
    w, h = dialog.width + 2 * pad, dialog.height + 2 * pad
    if aspect:
        w, h = max(w, round(h * aspect)), max(h, round(w / aspect))
    out = Image.new("RGBA", (w, h), bg + (255,))
    glow = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((out.width * 0.2, out.height * 0.3, out.width * 1.1, out.height * 1.3),
                                 fill=accent + (40,))
    out.alpha_composite(glow.filter(ImageFilter.GaussianBlur(120)))
    shadow = Image.new("RGBA", out.size, (0, 0, 0, 0))
    x, y = (w - dialog.width) // 2, (h - dialog.height) // 2
    ImageDraw.Draw(shadow).rounded_rectangle((x, y + 16, x + dialog.width, y + dialog.height + 16),
                                             radius=20, fill=(0, 0, 0, 160))
    out.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(26)))
    out.alpha_composite(rounded(dialog, 14), (x, y))
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
        cover = banner(shot(), ui)
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
        frames = []

        def run(dlg):
            for _ in range(6):                     # PgDn: os quadros da pose parada, um a um
                frames.append(card(grab(dlg), ui, GRID_ASPECT))
                dlg.go(1)
        on_exec(imageeditor.ImageEditor, run)
        win.sprites.edit_image()
        save_motion(frames, [260] * len(frames), "only-pixel-editor.webp")

    def s_command_palette():
        from charfactory.gui import dialogs
        win.show_page(an)
        base = shot()
        frames, durations = [], []

        def run(dlg):
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
            save_png(card(grab(dlg), ui, GRID_ASPECT), "only-transplant.png")
        on_exec(dialogs_tools.TransplantDialog, transplant)
        win.transplant_move()

        on_exec(movewizard.MoveWizardDialog, lambda dlg: save_png(card(grab(dlg), ui, GRID_ASPECT), "only-move-wizard.png"))
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
            save_png(card(grab(dlg), ui, GRID_ASPECT), "only-sheet.png")
        on_exec(dialogs.SheetDialog, slicer)
        win.sheet()

        on_exec(palettes12.PaletteSetDialog, lambda dlg: save_png(card(grab(dlg), ui, GRID_ASPECT), "only-palettes12.png"))
        win.show_page(win.sprites)
        win.sprites.open_palettes12()

        on_exec(dialogs.UnusedDialog, lambda dlg: save_png(card(grab(dlg), ui, GRID_ASPECT), "only-unused.png"))
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

    # ------------------------------------------------------------------ IA

    def s_ai():
        """O assistente cria um golpe do zero: escolhe as poses, monta as animações, escreve as
        duas fases, simula, corrige a caixa do chute que passava na frente do oponente e mostra o
        golpe no simulador. Nenhum provedor é chamado: os passos (ferramentas de verdade, no kfm)
        são feitos aqui, na ordem em que o modelo os pediria."""
        import json
        import re
        from charfactory.ai import keys as ai_keys
        from charfactory.ai.providers import Call
        from charfactory.tools import ops
        ai_keys.get = lambda name: "demo"
        ctx.settings.update(ai_provider="anthropic", ai_model_anthropic="claude-opus-5-5")
        pose(0, 640)
        win.toggle_assistant(True)
        p, host = win.assistant, win.ai_host
        host.turn_parts.clear()
        p.refresh()
        frames, durations = [], []

        def snap(ms: int, text: str | None = None) -> None:
            p._refresh_context()
            img = shot()
            frames.append(caption(img, text) if text else img)
            durations.append(ms)

        def step(name: str, args: dict, ms: int = 650):
            call = Call(str(len(p._steps)), name, args)
            p.on_event("tool", call)
            p._tick()
            snap(320)
            res = host.call(name, args)
            p.on_event("result", (call, res))
            p._tick()
            snap(ms)
            return res

        def say(text: str, ms: int = 1400) -> None:
            p.on_event("text", text)
            snap(ms)

        snap(1500)
        ask = "Create a new attack: he jumps forward kicking, then lands a combo and knocks the opponent far away"
        for k in range(0, len(ask), 4):
            p.input.setPlainText(ask[:k])
            snap(45)
        p.input.setPlainText(ask)
        snap(700)
        p.input.clear()
        p._add(("user", ask))
        p.show_busy(True)
        snap(800)
        say("I'll find the poses first.", 900)
        step("list_animations", {"search": "kick"})
        step("view_animations", {"numbers": [630, 640, 240, 1055]}, 1500)
        say("640 (jump strong kick) for the jump; the punches 200 and 210 and the strong kick 240 for "
            "the combo. Building both animations with their boxes.", 1600)
        step("build_animation", {"number": 1500, "frames": AI_JUMP_KICK})
        an.select_action(1500)
        step("build_animation", {"number": 1501, "frames": AI_COMBO}, 900)
        an.select_action(1501)
        step("create_move", {"state": 1500, "anim": 1500, "kind": "special", "command": "~D, DB, B, b",
                             "name": "Flying Kick Combo"})
        step("set_state", {"number": 1500, "text": AI_AIR_STATE, "replace": True})
        step("set_state", {"number": 1501, "text": AI_COMBO_STATE})
        sim = json.loads(step("simulate_state", {"number": 1500}, 900).text)
        hits = [e for e in sim["events"] if e["kind"] == "hit"]
        say(f"The combo lands {len(hits)} hits, but the flying kick passes in front of him: its box "
            "covers only the foot. Widening it to the whole leg.", 1800)
        text = ops.get_action_text(ctx.char, 1500)
        text = re.sub(r"Clsn1: 1\n Clsn1\[0\] = [^\n]+",
                      "Clsn1: 2\n Clsn1[0] = 13, -48, 43, -33\n Clsn1[1] = 43, -44, 73, -24", text)
        step("set_animation", {"text": text})
        sim = json.loads(step("simulate_state", {"number": 1500}, 900).text)
        hits = [e for e in sim["events"] if e["kind"] == "hit"]
        say(f"Done: **Flying Kick Combo** on `D, DB, B + b`.\n\n"
            f"- **State 1500**: jumps forward kicking (animation 1500)\n"
            f"- **State 1501**: punch, strong punch and a launcher kick (animation 1501)\n\n"
            f"Simulated: {len(hits)} hits, {sum(e.get('damage') or 0 for e in hits)} damage, and the last "
            f"one knocks him far away. Here it is in the simulator.", 2600)
        p.on_done()
        snap(1200)

        # o golpe pronto no simulador, tick a tick (a cada 2 ticks, em tempo real)
        if simulate(1500):
            for tick in range(0, sp.slider.maximum() + 1, 2):
                sp.slider.setValue(tick)
                wait(lambda: not sp._rendering and sp._key(tick) in sp.cache, 20)
                p._refresh_context()
                frames.append(caption(shot(), "The new move in the simulator, tick by tick"))
                durations.append(34)
            durations[-1] = 2600
        save_motion(frames, durations, "ai-assistant.webp")
        while ctx.undo():
            pass
        p.new_chat()
        win.toggle_assistant(False)

    def s_mcp():
        """Um cliente MCP de verdade (pedidos HTTP ao servidor da janela) à esquerda e o editor
        mudando junto à direita; e a aba que mostra a configuração de cada cliente."""
        import json
        import socket
        import threading
        import urllib.request
        from charfactory.gui.aipanel import AISettingsDialog
        ctx.settings.update(ai_mcp_enabled=True, ai_mcp_token="your-token", ai_mcp_port=47913)
        win.mcp.apply()
        if win.mcp.server is None:                 # a porta padrão está em uso (o app aberto)
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                ctx.settings["ai_mcp_port"] = sock.getsockname()[1]
            win.mcp.apply()
        srv = win.mcp.server

        dlg = AISettingsDialog(ctx, win.mcp, win, tab=1)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        dlg.show()
        dlg.client.setCurrentText("Claude Code")
        save_png(card(grab(dlg), ui, GRID_ASPECT), "ai-connect.png")
        dlg.reject()

        def rpc(method: str, params: dict | None = None) -> dict:
            body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}).encode()
            req = urllib.request.Request(srv.url, body, headers={"Content-Type": "application/json",
                                                                 "Authorization": f"Bearer {win.mcp.token()}"})
            out: list = []
            t = threading.Thread(target=lambda: out.append(json.loads(urllib.request.urlopen(req, timeout=60).read())))
            t.start()
            while t.is_alive():                    # a ferramenta roda na thread da interface
                settle(1)
            return out[0]["result"]

        def call(name: str, args: dict) -> dict | str:
            text = rpc("tools/call", {"name": name, "arguments": args})["content"][0]["text"]
            try:
                return json.loads(text)
            except ValueError:
                return text

        def rgb(h: str) -> tuple[int, int, int]:
            return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))
        f, fb = font(["JetBrainsMono-Regular.ttf"], 27), font(["JetBrainsMono-Bold.ttf"], 27)

        def pane(lines: list[tuple[str, str]], w: int, h: int) -> Image.Image:
            img = Image.new("RGBA", (w, h), rgb(ui["panel"]) + (255,))
            d = ImageDraw.Draw(img)
            d.rectangle((0, 0, w, 64), fill=rgb(ui["window"]))
            for i, c in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
                d.ellipse((28 + i * 34, 23, 46 + i * 34, 41), fill=c)
            d.text((w / 2, 32), "MCP client  →  Char Factory", font=f, fill=rgb(ui["text_dim"]), anchor="mm")
            y = 96
            for kind, text in lines:
                color = {"task": rgb(ui["text"]), "req": rgb(ui["accent"]), "res": rgb(ui["text_dim"]),
                         "note": rgb(ui["warning"])}[kind]
                prefix = {"task": "› ", "req": "→ ", "res": "← ", "note": "# "}[kind]
                wrapped, line = [], prefix + text
                while len(line) > 54:
                    cut = line.rfind(" ", 0, 54)
                    cut = cut if cut > 20 else 54
                    wrapped.append(line[:cut])
                    line = "   " + line[cut:].lstrip()
                wrapped.append(line)
                for ln in wrapped:
                    d.text((36, y), ln, font=fb if kind in ("task", "req") else f, fill=color)
                    y += 38
                y += 14 if kind == "res" else 0
            return img

        def frame(lines: list[tuple[str, str]]) -> Image.Image:
            screen = shot()
            screen = screen.resize((1440, round(screen.height * 1440 / screen.width)), Image.Resampling.LANCZOS)
            gap, tw = 40, 1000
            out = Image.new("RGBA", (tw + screen.width + 3 * gap, screen.height + 2 * gap), rgb(ui["window"]) + (255,))
            glow = Image.new("RGBA", out.size, (0, 0, 0, 0))
            ImageDraw.Draw(glow).ellipse((out.width * 0.3, out.height * 0.2, out.width * 1.1, out.height * 1.4),
                                         fill=rgb(ui["accent"]) + (45,))
            out.alpha_composite(glow.filter(ImageFilter.GaussianBlur(140)))
            out.alpha_composite(rounded(pane(lines, tw, screen.height), 18), (gap, gap))
            out.alpha_composite(rounded(screen, 18), (tw + 2 * gap, gap))
            return out

        pose(0, 430)
        act = ctx.char.anims.get(430)
        lines = [("note", f"connected to {srv.url}"),
                 ("task", "Make the crouching light kick faster and stronger")]
        frames, durations = [frame(lines)], [1800]

        def show(req: str, res: str, ms: int = 1500) -> None:
            lines.append(("req", req))
            frames.append(frame(lines))
            durations.append(450)
            lines.append(("res", res))
            frames.append(frame(lines))
            durations.append(ms)

        init = rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                  "clientInfo": {"name": "demo", "version": "1"}})
        count = len(rpc("tools/list")["tools"])
        show("initialize", f"{init['serverInfo']['title']} {init['serverInfo']['version']} · {count} tools", 1000)
        move = call("get_move", {"number": 430})
        cmds = [c["sequence"] for e in move.get("entries", []) if isinstance(e, dict) for c in e["commands"]]
        verdict = (move.get("simulation") or {}).get("verdict", "")
        show('get_move {"number": 430}', f'state 430 "{ctx.char.anims.name_of(430)}" · input '
             f'{cmds[0] if cmds else "-"} · {verdict.split(" on an opponent")[0]}')
        before = act.total_time
        faster = [{"frame": i + 1, "time": fr.time - 1} for i, fr in enumerate(act.frames[:-1]) if fr.time > 1][:2]
        res = call("edit_animation", {"number": 430, "frames": faster})
        show(f'edit_animation {{"number": 430, "frames": {json.dumps(faster)}}}',
             f"animation 430: {before} → {res['total_time']} ticks")
        hit = next(c for c in ctx.char.all_statedefs()[430][0].controllers if c.type.lower() == "hitdef")
        res = call("edit_state", {"number": 430, "target": hit.label, "set": [{"key": "damage", "value": "30, 4"}]})
        show(f'edit_state {{"number": 430, "target": "{hit.label}", "set": damage = 30, 4}}',
             f"{res['in']} {', '.join(res['lines_now'])}")
        sim = call("simulate_state", {"number": 430})
        adv = sim.get("advantage")
        show('simulate_state {"number": 430}', f"{sim['outcome']} · startup {sim['startup']}"
             + (f" · advantage {adv:+}" if isinstance(adv, (int, float)) else ""), 4500)
        save_motion(frames, durations, "ai-mcp.webp")
        while ctx.undo():
            pass
        ctx.settings["ai_mcp_enabled"] = False
        win.mcp.apply()

    scenes = {"animations": s_animations, "editors": s_editors, "pixel-editor": s_image_editor,
              "command-palette": s_command_palette, "themes": s_themes,
              "compare": s_compare, "timeline": s_timeline, "clsn": s_clsn, "tools": s_tools, "cli": s_cli,
              "ai": s_ai, "mcp": s_mcp}
    for name, fn in scenes.items():
        if not wanted or name in wanted:
            fn()

    win.close()
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
