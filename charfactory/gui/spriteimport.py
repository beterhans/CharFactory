"""Janela "Importar imagens": onde entram (grupo e índice, ou pelo nome do arquivo, de 1 em 1 ou
de 10 em 10), o eixo (9 âncoras ou X/Y), que paleta usam (a do personagem, adaptar a uma do
SFF, manter os índices trocando a paleta, uma própria feita das cores da imagem ou cores reais
em PNG 32 bits), que cor é o fundo transparente, se sprites iguais viram link e uma prévia."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QMessageBox, QPushButton, QRadioButton, QScrollArea, QSpinBox, QToolButton,
                               QVBoxLayout, QWidget)

from ..tools import spriteimport as SI
from .canvas import pil_to_qimage
from .context import AppContext
from .widgets import hint_label
from ..i18n import tr

PREVIEW = 300
ANCHOR_GRID = (("tl", "t", "tr"), ("l", "c", "r"), ("bl", "b", "br"))


def _checker(w: int, h: int) -> Image.Image:
    """Xadrez atrás da prévia: o que é transparente aparece como transparente."""
    y, x = np.mgrid[0:h, 0:w]
    a = np.where(((x // 8) + (y // 8)) % 2, 70, 100).astype(np.uint8)
    return Image.fromarray(np.stack([a, a, a, np.full_like(a, 255)], axis=2), "RGBA")


def _pixmap(img: Image.Image, axis: tuple[int, int] | None = None) -> QPixmap:
    """A imagem ampliada sem borrar (até caber em PREVIEW), sobre xadrez, com a cruz do eixo."""
    img = img.convert("RGBA")
    k = max(1, min(PREVIEW // max(img.width, 1), PREVIEW // max(img.height, 1), 8))
    big = img.resize((img.width * k, img.height * k), Image.NEAREST) if k > 1 else img
    scale = k
    if max(big.size) > PREVIEW:
        f = PREVIEW / max(big.size)
        big = big.resize((max(1, int(big.width * f)), max(1, int(big.height * f))), Image.NEAREST)
        scale = k * f
    # a área cresce até o eixo (ele pode cair fora da imagem recortada, ou na borda)
    ex, ey = (axis[0] * scale, axis[1] * scale) if axis is not None else (0, 0)
    left, top = int(max(8, 8 - ex)), int(max(8, 8 - ey))
    right, bottom = int(max(8, ex - big.width + 8)), int(max(8, ey - big.height + 8))
    bg = _checker(big.width + left + right, big.height + top + bottom)
    bg.alpha_composite(big, (left, top))
    if axis is not None:
        x, y = left + ex, top + ey
        d = ImageDraw.Draw(bg)
        for col, w in (((0, 0, 0, 255), 3), ((255, 230, 0, 255), 1)):
            d.line([(x - 7, y), (x + 7, y)], fill=col, width=w)
            d.line([(x, y - 7), (x, y + 7)], fill=col, width=w)
    return QPixmap.fromImage(pil_to_qimage(bg))


def _swatch_icon(colors: list, w: int = 60, h: int = 12) -> QIcon:
    pm = QPixmap(w, h)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    take = colors[1:] or colors
    step = max(1, len(take) // 10)
    take = take[::step][:10]
    for k, c in enumerate(take):
        p.fillRect(round(k * w / len(take)), 0, round(w / len(take)) + 1, h, QColor(*c[:3]))
    p.end()
    return QIcon(pm)


def _palette_strip(colors: list) -> QPixmap:
    """As cores da paleta que vai ser usada, 32 por linha (a 1ª, o fundo, com um contorno)."""
    n = len(colors)
    cols, cell = 32, 9
    rows = max(1, (n + cols - 1) // cols)
    pm = QPixmap(cols * cell, rows * cell)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    for i, c in enumerate(colors):
        x, y = (i % cols) * cell, (i // cols) * cell
        p.fillRect(x, y, cell - 1, cell - 1, QColor(*c[:3]))
        if i == 0:
            p.setPen(QColor("#ffffff"))
            p.drawRect(x, y, cell - 2, cell - 2)
    p.end()
    return pm


def _anchor_icon(key: str) -> QIcon:
    """Quadrado com a cruz na posição da âncora."""
    pm = QPixmap(22, 22)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QColor("#9aa0a6"))
    p.drawRect(5, 5, 12, 12)
    fx, fy = SI.ANCHORS[key]
    x, y = 5 + 12 * fx, 5 + 12 * fy
    p.setPen(QColor("#ffd400"))
    p.drawLine(int(x - 4), int(y), int(x + 4), int(y))
    p.drawLine(int(x), int(y - 4), int(x), int(y + 4))
    p.end()
    return QIcon(pm)


class ImportSpritesDialog(QDialog):
    def __init__(self, ctx: AppContext, paths: list[str], group: int, item: int, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.char = ctx.char
        self.paths = list(paths)
        self.images = SI.open_images(self.paths)
        self.result: dict | None = None
        self.setWindowTitle(tr("Import images"))
        self.setMinimumSize(1120, 720)
        saved = ctx.settings.get("sprite_import") or {}

        # ------------------------------------------------ onde
        self.files = QLabel()
        self.files.setWordWrap(True)
        self.from_name = QCheckBox(tr("Group and index from the file name (e.g. kfm_200-3.png)"))
        self.from_name.setChecked(bool(saved.get("from_name", False)))
        self.group = QSpinBox()
        self.group.setRange(0, 99999)
        self.group.setValue(group)
        self.item = QSpinBox()
        self.item.setRange(0, 99999)
        self.item.setValue(item)
        self.step1 = QRadioButton("1, 2, 3, 4…")
        self.step10 = QRadioButton("10, 20, 30…")
        (self.step10 if int(saved.get("step", 1)) == 10 else self.step1).setChecked(True)
        self.where_note = QLabel()
        self.where_note.setObjectName("dim")
        self.where_note.setWordWrap(True)
        where_box = QGroupBox(tr("Where"))
        wf = QFormLayout(where_box)
        wf.addRow(tr("Images"), self.files)
        wf.addRow(self.from_name)
        num = QHBoxLayout()
        num.addWidget(self.group)
        num.addWidget(QLabel(","))
        num.addWidget(self.item)
        wf.addRow(tr("Group, index"), num)
        steps = QHBoxLayout()
        steps.addWidget(self.step1)
        steps.addWidget(self.step10)
        steps.addStretch()
        wf.addRow(tr("Numbers"), steps)
        wf.addRow(self.where_note)

        # ------------------------------------------------ eixo
        axis_box = QGroupBox(tr("Axis"))
        av = QHBoxLayout(axis_box)
        grid = QGridLayout()
        self.anchor_buttons: dict[str, QToolButton] = {}
        self.anchors = QButtonGroup(self)
        for r, row in enumerate(ANCHOR_GRID):
            for c, key in enumerate(row):
                b = QToolButton()
                b.setCheckable(True)
                b.setIcon(_anchor_icon(key))
                b.setIconSize(QSize(22, 22))
                b.setToolTip({"b": tr("Bottom center (feet on the ground)")}.get(key, ""))
                b.clicked.connect(lambda _=False, k=key: self._set_anchor(k))
                self.anchors.addButton(b)
                self.anchor_buttons[key] = b
                grid.addWidget(b, r, c)
        av.addLayout(grid)
        self.ax = QSpinBox()
        self.ay = QSpinBox()
        for sb in (self.ax, self.ay):
            sb.setRange(-9999, 9999)
            sb.valueChanged.connect(self._axis_typed)
        xy = QFormLayout()
        xy.addRow("X", self.ax)
        xy.addRow("Y", self.ay)
        av.addLayout(xy)
        av.addWidget(hint_label(tr("The yellow cross in the preview is the axis. The buttons place it on the "
                                   "image; X and Y set it exactly for every image.")), 1)
        self.anchor = saved.get("anchor", "b") if saved.get("anchor", "b") in SI.ANCHORS else "b"

        # ------------------------------------------------ cores
        colors = QGroupBox(tr("Colors"))
        cv = QVBoxLayout(colors)
        self.mode = QButtonGroup(self)
        has_char = self.char.sprites.find_palette(1, 1) >= 0
        self.r_char = QRadioButton(tr("Character palette (1,1)"))
        self.r_char.setEnabled(has_char)
        self.r_pal = QRadioButton(tr("Adapt the image to the palette"))
        self.r_swap = QRadioButton(tr("Keep the indices and use the palette (swap)"))
        self.pal_combo = QComboBox()
        for p in self.char.sprites.palettes:
            self.pal_combo.addItem(_swatch_icon(p.colors), f"{p.group},{p.item}  ({len(p.colors)})", (p.group, p.item))
        self.pal_combo.setIconSize(QSize(60, 12))
        self.r_own = QRadioButton(tr("Own palette, made from the image colors"))
        self.own_shared = QCheckBox(tr("One palette for all the images"))
        self.own_shared.setChecked(saved.get("shared", True))
        self.own_reuse = QCheckBox(tr("Use an identical palette if the SFF has one"))
        self.own_reuse.setChecked(saved.get("reuse", True))
        self.own_colors = QSpinBox()
        self.own_colors.setRange(2, 255)
        self.own_colors.setValue(int(saved.get("colors", 255)))
        self.own_auto = QCheckBox(tr("Automatic number"))
        self.own_auto.setChecked(True)
        self.own_g = QSpinBox()
        self.own_g.setRange(0, 99999)
        self.own_i = QSpinBox()
        self.own_i.setRange(0, 99999)
        self.r_true = QRadioButton(tr("True colors (32-bit PNG)"))
        self.reversed = QCheckBox(tr("Reversed palette (the last color is the background)"))
        self.dither = QCheckBox(tr("Dithering (smooths gradients when the colors do not fit)"))
        self.dither.setChecked(bool(saved.get("dither", False)))
        for k, r in enumerate((self.r_char, self.r_pal, self.r_swap, self.r_own, self.r_true)):
            self.mode.addButton(r, k)
        cv.addWidget(self.r_char)
        cv.addWidget(hint_label(tr("Changes with the player's 12 palettes: for the character's body.")))
        pal_row = QHBoxLayout()
        pal_row.addWidget(QLabel(tr("SFF palette")))
        pal_row.addWidget(self.pal_combo, 1)
        cv.addWidget(self.r_pal)
        cv.addWidget(self.r_swap)
        cv.addLayout(pal_row)
        cv.addWidget(self.r_own)
        own = QGridLayout()
        own.setContentsMargins(22, 0, 0, 0)
        own.addWidget(self.own_shared, 0, 0, 1, 2)
        cnt = QHBoxLayout()
        cnt.addWidget(QLabel(tr("Up to")))
        cnt.addWidget(self.own_colors)
        cnt.addWidget(QLabel(tr("colors")))
        cnt.addStretch()
        own.addLayout(cnt, 0, 2)
        own.addWidget(self.own_reuse, 1, 0, 1, 3)
        numrow = QHBoxLayout()
        numrow.addWidget(self.own_auto)
        numrow.addWidget(self.own_g)
        numrow.addWidget(QLabel(","))
        numrow.addWidget(self.own_i)
        numrow.addStretch()
        own.addWidget(QLabel(tr("Palette number")), 2, 0)
        own.addLayout(numrow, 2, 1, 1, 2)
        cv.addLayout(own)
        cv.addWidget(self.r_true)
        cv.addWidget(hint_label(tr("No color limit, for very detailed images. MUGEN 1.1 and Ikemen only; PalFX and "
                                   "the player's palettes do not change these sprites.")))
        cv.addWidget(self.reversed)
        cv.addWidget(self.dither)
        mode = saved.get("mode", "char" if has_char else "own")
        {"char": self.r_char, "palette": self.r_pal, "swap": self.r_swap, "own": self.r_own,
         "truecolor": self.r_true}.get(mode, self.r_own).setChecked(True)
        if not has_char and self.r_char.isChecked():
            self.r_own.setChecked(True)

        # ------------------------------------------------ fundo, recorte e iguais
        bgbox = QGroupBox(tr("Transparent background (index 0)"))
        bv = QHBoxLayout(bgbox)
        self.trans = QComboBox()
        for key, text in (("auto", tr("Automatic")), ("alpha", tr("Image transparency (alpha)")),
                          ("topleft", tr("Color of the top-left corner")), ("index0", tr("Index 0 of the image")),
                          ("color", tr("A color I pick…"))):
            self.trans.addItem(text, key)
        self.trans.setCurrentIndex(max(0, self.trans.findData(saved.get("trans", "auto"))))
        self.trans_color = tuple(saved.get("trans_color") or (255, 0, 255))
        self.color_btn = QPushButton()
        self.color_btn.setFixedWidth(40)
        self.color_btn.clicked.connect(self._pick_color)
        bv.addWidget(self.trans, 1)
        bv.addWidget(self.color_btn)
        self.autocrop = QComboBox()
        self.autocrop.addItem(tr("Crop the empty border"), True)
        self.autocrop.addItem(tr("Don't crop the image"), False)
        self.autocrop.setCurrentIndex(0 if saved.get("autocrop", True) else 1)
        self.share = QComboBox()
        self.share.addItem(tr("Share identical sprites"), "share")
        self.share.addItem(tr("Don't share identical sprites"), "no")
        self.share.addItem(tr("Ask to share identical sprites"), "ask")
        self.share.setCurrentIndex(max(0, self.share.findData(saved.get("share", "share"))))
        self.share.setToolTip(tr("An image equal to a sprite that already exists becomes a link to it: "
                                 "the SFF keeps the data once"))

        left_w = QWidget()
        left = QVBoxLayout(left_w)
        left.setContentsMargins(0, 0, 6, 0)
        left.addWidget(where_box)
        left.addWidget(colors)
        left.addWidget(bgbox)
        left.addWidget(self.autocrop)
        left.addWidget(self.share)
        left.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(left_w)

        # ------------------------------------------------ prévia
        self.which = QComboBox()
        for p in self.paths:
            self.which.addItem(Path(p).name)
        self.which.setVisible(len(self.paths) > 1)
        self.before = QLabel()
        self.after = QLabel()
        for lb in (self.before, self.after):
            lb.setMinimumSize(PREVIEW + 16, PREVIEW + 16)
            lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pics = QHBoxLayout()
        for title, lb in ((tr("Original"), self.before), (tr("As it will be"), self.after)):
            col = QVBoxLayout()
            col.addWidget(QLabel(f"<b>{title}</b>"))
            col.addWidget(lb)
            pics.addLayout(col)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setObjectName("infoChip")
        self.strip = QLabel()
        right = QVBoxLayout()
        right.addWidget(self.which)
        right.addLayout(pics)
        right.addWidget(axis_box)
        right.addWidget(self.info)
        right.addWidget(QLabel(tr("Palette used (the outlined color is the background):")))
        right.addWidget(self.strip)
        right.addStretch()

        scroll.setMinimumWidth(500)
        body = QHBoxLayout()
        body.addWidget(scroll, 5)
        body.addLayout(right, 6)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Import"))
        bb.accepted.connect(self.do_import)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(body, 1)
        lay.addWidget(bb)

        for w in (self.r_char, self.r_pal, self.r_swap, self.r_own, self.r_true, self.own_shared, self.own_reuse,
                  self.own_auto, self.reversed, self.dither):
            w.toggled.connect(self.update_preview)
        for w in (self.pal_combo, self.trans, self.which, self.autocrop):
            w.currentIndexChanged.connect(self.update_preview)
        for w in (self.own_colors, self.own_g, self.own_i):
            w.valueChanged.connect(self.update_preview)
        for w in (self.group, self.item):
            w.valueChanged.connect(self._where)
        for w in (self.from_name, self.step1, self.step10):
            w.toggled.connect(self._where)
        self.which.currentIndexChanged.connect(lambda _: self._set_anchor(self.anchor))
        self._set_anchor(self.anchor)
        self._where()
        self.update_preview()

    # ------------------------------------------------------------ opções

    def options(self) -> SI.ImportOptions:
        mode = ["char", "palette", "swap", "own", "truecolor"][max(0, self.mode.checkedId())]
        return SI.ImportOptions(
            mode=mode, palette=self.pal_combo.currentData(), shared=self.own_shared.isChecked(),
            colors=self.own_colors.value(), reuse=self.own_reuse.isChecked(),
            palette_number=None if self.own_auto.isChecked() else (self.own_g.value(), self.own_i.value()),
            reversed=self.reversed.isChecked(), dither=self.dither.isChecked(),
            trans=self.trans.currentData(), trans_color=self.trans_color,
            autocrop=bool(self.autocrop.currentData()), from_name=self.from_name.isChecked(),
            step=10 if self.step10.isChecked() else 1, anchor=self.anchor,
            axis=(self.ax.value(), self.ay.value()), share=self.share.currentData() != "no")

    def _current(self) -> Image.Image:
        return self.images[max(0, self.which.currentIndex())]

    def _set_anchor(self, key: str) -> None:
        """Âncora escolhida: o X/Y mostra onde ela cai na imagem da prévia."""
        self.anchor = key
        for k, b in self.anchor_buttons.items():
            b.setChecked(k == key)
        if key in SI.ANCHORS:
            im = self._current()
            x, y = SI.axis_for(im.width, im.height, SI.ImportOptions(anchor=key))
            for sb, v in ((self.ax, x), (self.ay, y)):
                sb.blockSignals(True)
                sb.setValue(v)
                sb.blockSignals(False)
        self.update_preview()

    def _axis_typed(self, *_) -> None:
        """X/Y digitado: eixo exato, o mesmo em todas as imagens."""
        self.anchor = "custom"
        for b in self.anchor_buttons.values():
            b.setChecked(False)
        self.update_preview()

    def _pick_color(self) -> None:
        c = QColorDialog.getColor(QColor(*self.trans_color), self, tr("Background color"))
        if c.isValid():
            self.trans_color = (c.red(), c.green(), c.blue())
            self.trans.setCurrentIndex(self.trans.findData("color"))
            self.update_preview()

    def _where(self, *_) -> None:
        n = len(self.paths)
        names = ", ".join(Path(p).name for p in self.paths[:4]) + (" …" if n > 4 else "")
        self.files.setText(f"{n} · {names}")
        opts = self.options()
        tg = SI.targets(self.paths, self.group.value(), self.item.value(), opts)
        by_name = sum(1 for p in self.paths if opts.from_name and SI.parse_name(p))
        self.group.setEnabled(by_name < n)
        self.item.setEnabled(by_name < n)
        shown = ", ".join(f"{g},{i}" for g, i in tg[:4]) + (" …" if n > 4 else "")
        taken = [t for t in tg if self.char.sprites.find(*t) is not None]
        self.where_note.setText(shown
                                + (tr(" · {0} from the file name").format(by_name) if by_name else "")
                                + (tr(" · replaces {0} sprite(s) that already exist").format(len(taken)) if taken else ""))

    # ------------------------------------------------------------ prévia

    def update_preview(self, *_) -> None:
        if not hasattr(self, "info"):
            return                               # ainda montando a janela
        k = max(0, self.which.currentIndex())
        opts = self.options()
        self.pal_combo.setEnabled(opts.mode in ("palette", "swap"))
        self.own_shared.setVisible(len(self.paths) > 1)
        for w in (self.own_shared, self.own_colors, self.own_reuse, self.own_auto):
            w.setEnabled(opts.mode == "own")
        for w in (self.own_g, self.own_i):
            w.setEnabled(opts.mode == "own" and not self.own_auto.isChecked())
        self.dither.setEnabled(opts.mode in ("char", "palette", "own"))
        self.reversed.setEnabled(any(im.mode == "P" for im in self.images) and opts.mode != "truecolor")
        im = self._current()
        ax, ay = SI.axis_for(im.width, im.height, opts)
        self.before.setPixmap(_pixmap(im, (ax, ay)))
        try:
            imgs = self.images if opts.mode == "own" and opts.shared else [im]
            conv = SI.convert(imgs, self.char, opts)[k if len(imgs) > 1 else 0]
        except ValueError as e:
            self.info.setText(str(e))
            self.after.clear()
            self.strip.clear()
            return
        res = conv["image"]
        shown_img = res.convert("RGBA") if res.mode == "RGBA" else self._rgba(res)
        if opts.autocrop:
            box = SI._crop(res, conv["mask"])
            if box is not None:
                shown_img = shown_img.crop(box)
                ax, ay = ax - box[0], ay - box[1]
        self.after.setPixmap(_pixmap(shown_img, (ax, ay)))
        mask, bg = SI.background(SI.reverse_palette(im) if opts.reversed else im, opts)
        # o quadradinho mostra a cor que vai virar o fundo (a detectada, ou a escolhida)
        shown = tuple(opts.trans_color) if opts.trans == "color" else bg
        self.color_btn.setStyleSheet(f"background: rgb{tuple(shown)};" if shown else "")
        self.color_btn.setToolTip(tr("Background color: {0}").format(
            "#%02x%02x%02x" % tuple(shown)) if shown else tr("Background from the image transparency (alpha)"))
        n = SI.count_colors(im, mask)
        msg = tr("{0} colors in the image (without the background)").format(n)
        if opts.mode == "truecolor":
            msg += tr(" · kept as they are")
        elif opts.mode == "own":
            msg += tr(" · fits in one palette") if n <= opts.colors else \
                tr(" · reduced to {0}: for every color use True colors").format(opts.colors)
        elif opts.mode == "swap":
            msg += tr(" · the indices stay as they are")
        if opts.mode in ("char", "palette") and conv["lost"] > 0.04:
            msg += tr(" · <b>the colors change a lot</b> in this palette: try Own palette or True colors")
        self.info.setText(msg)
        self.strip.setPixmap(_palette_strip(conv["colors"]) if conv["colors"] else QPixmap())
        self.strip.setVisible(bool(conv["colors"]))

    @staticmethod
    def _rgba(res: Image.Image) -> Image.Image:
        """Indexada com o índice 0 transparente, como o motor desenha."""
        rgba = np.array(res.convert("RGBA"))
        rgba[np.asarray(res) == 0, 3] = 0
        return Image.fromarray(rgba, "RGBA")

    # ------------------------------------------------------------ importar

    def do_import(self) -> None:
        opts = self.options()
        self.ctx.settings["sprite_import"] = {
            "mode": opts.mode, "shared": opts.shared, "colors": opts.colors, "reuse": opts.reuse,
            "dither": opts.dither, "trans": opts.trans, "trans_color": list(opts.trans_color or ()),
            "autocrop": opts.autocrop, "from_name": opts.from_name, "step": opts.step,
            "anchor": opts.anchor if opts.anchor in SI.ANCHORS else "b", "share": self.share.currentData()}
        if self.share.currentData() == "ask":
            opts.share = QMessageBox.question(
                self, tr("Share identical sprites"),
                tr("If an image is equal to a sprite that already exists, make it a link to that sprite?")) \
                == QMessageBox.StandardButton.Yes
        try:
            self.result = SI.import_images(self.char, self.paths, self.group.value(), self.item.value(), opts)
        except ValueError as e:
            self.info.setText(str(e))
            return
        self.accept()


def ask_images(parent, many: bool = True) -> list[str]:
    filt = tr("Images (*.png *.pcx *.gif *.bmp *.jpg *.jpeg *.webp *.tga)")
    if many:
        paths, _ = QFileDialog.getOpenFileNames(parent, tr("Import images (in name order)"), "", filt)
        return sorted(paths)
    path, _ = QFileDialog.getOpenFileName(parent, tr("Image"), "", filt)
    return [path] if path else []
