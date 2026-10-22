"""Importar imagens como sprites: paleta do personagem, de outra paleta do SFF, própria (com o
fundo no índice 0) ou em cores reais (PNG 32 bits) para o que não cabe numa paleta."""
import shutil

import numpy as np
import pytest
from PIL import Image

from charfactory import project
from charfactory.tools import spriteimport as SI


@pytest.fixture()
def kfm(mugen_dir, tmp_path):
    work = tmp_path / "chars" / "kfm"
    shutil.copytree(mugen_dir / "chars" / "kfm", work)
    return project.load(work / "kfm.def")


def _figure(tmp_path, name="fig.png", bg=(255, 0, 255)):
    """Fundo magenta e um boneco de três cores, uma delas preta (não pode virar buraco)."""
    a = np.zeros((40, 30, 3), np.uint8)
    a[:] = bg
    a[5:35, 10:20] = (200, 40, 40)
    a[5:12, 10:20] = (0, 0, 0)
    a[20:25, 12:18] = (30, 120, 220)
    p = tmp_path / name
    Image.fromarray(a, "RGB").save(p)
    return p


def test_own_palette_keeps_the_colors_with_the_background_at_index_0(kfm, tmp_path):
    p = _figure(tmp_path)
    r = SI.import_images(kfm, [p], 7000, 0, SI.ImportOptions(mode="own"))
    s = kfm.sprites
    spr = s.find(7000, 0)
    pal = s.palettes[spr.palette_index]
    assert pal.group != 1 and pal.colors[0] == (255, 0, 255)       # o fundo no índice 0
    assert sorted(pal.colors[1:]) == sorted([(0, 0, 0), (200, 40, 40), (30, 120, 220)])
    px = np.frombuffer(s.pixels(spr), np.uint8).reshape(spr.height, spr.width)
    assert (px > 0).all() and (spr.width, spr.height) == (10, 30)   # recortado; o preto não vira 0
    assert r["lost"] == 0


def test_indexed_image_keeps_its_palette_moving_the_transparent_index(kfm, tmp_path):
    im = Image.new("P", (8, 8), 5)
    im.putpalette([10, 10, 10] * 5 + [255, 0, 255] + [250, 200, 0] * 250)
    for x in range(2, 6):
        im.putpixel((x, 4), 6)
    p = tmp_path / "idx.png"
    im.save(p, transparency=5)
    SI.import_images(kfm, [p], 7001, 0, SI.ImportOptions(mode="own", autocrop=False))
    s = kfm.sprites
    spr = s.find(7001, 0)
    pal = s.palettes[spr.palette_index].colors
    px = np.frombuffer(s.pixels(spr), np.uint8)
    assert pal[0] == (255, 0, 255) and set(px) == {0, 6} and pal[6] == (250, 200, 0)


def test_character_palette_and_other_palette_and_shared_batch(kfm, tmp_path):
    a, b = _figure(tmp_path, "a.png"), _figure(tmp_path, "b.png")
    s = kfm.sprites
    SI.import_images(kfm, [a], 7002, 0, SI.ImportOptions(mode="char"))
    assert s.find(7002, 0).palette_index == s.find_palette(1, 1)
    SI.import_images(kfm, [a], 7003, 0, SI.ImportOptions(mode="palette", palette=(9000, 1)))
    assert s.find(7003, 0).palette_index == s.find_palette(9000, 1)
    r = SI.import_images(kfm, [a, b], 1, 50, SI.ImportOptions(mode="own", shared=True))
    assert s.find(1, 50).palette_index == s.find(1, 51).palette_index
    assert r["palette"][0] != 1                                       # nunca vira paleta do jogador


def test_too_many_colors_reduce_or_go_truecolor(kfm, tmp_path):
    y, x = np.mgrid[0:64, 0:64]
    a = np.stack([x * 4, y * 4, (x + y) * 2], axis=2).astype(np.uint8)   # 4096 cores
    a[:4, :4] = (0, 255, 0)
    p = tmp_path / "grad.png"
    Image.fromarray(a, "RGB").save(p)
    opts = SI.ImportOptions(mode="own", trans="color", trans_color=(0, 255, 0), autocrop=False)
    im = SI.open_images([p])[0]
    mask, _ = SI.background(im, opts)
    assert SI.count_colors(im, mask) > 255
    r = SI.import_images(kfm, [p], 7004, 0, opts)
    assert 0 < r["lost"] < 0.05 and len(kfm.sprites.palettes[kfm.sprites.find(7004, 0).palette_index].colors) == 256
    SI.import_images(kfm, [p], 7005, 0, SI.ImportOptions(mode="truecolor", trans="color", trans_color=(0, 255, 0)))
    spr = kfm.sprites.find(7005, 0)
    img = kfm.sprites.image(spr)
    assert spr.is_truecolor and img.getpixel((10, 10))[3] == 255
    dither = SI.convert([im], kfm, SI.ImportOptions(mode="char", dither=True, trans="color", trans_color=(0, 255, 0)))
    assert (np.asarray(dither[0]["image"])[4:, 4:] > 0).all()


def test_numbers_from_name_step_and_axis_anchor(kfm, tmp_path):
    a = _figure(tmp_path, "kfm_7300-4.png")
    b = _figure(tmp_path, "sem numero.png")
    opts = SI.ImportOptions(mode="own", from_name=True, step=10, anchor="tl", autocrop=False)
    assert SI.targets([a, b], 7301, 0, opts) == [(7300, 4), (7301, 0)]
    assert SI.targets([b, b], 7301, 0, SI.ImportOptions(step=10)) == [(7301, 0), (7301, 10)]
    SI.import_images(kfm, [a, b], 7301, 0, opts)
    spr = kfm.sprites.find(7300, 4)
    assert spr is not None and (spr.axis_x, spr.axis_y) == (0, 0)
    assert SI.axis_for(30, 40, SI.ImportOptions(anchor="c")) == (15, 20)
    assert SI.axis_for(30, 40, SI.ImportOptions(anchor="custom", axis=(7, 9))) == (7, 9)


def test_swap_reversed_reuse_and_share(kfm, tmp_path):
    s = kfm.sprites
    # trocar a paleta: os índices como estão, apontando para a 1,1
    im = Image.new("P", (6, 6), 0)
    im.putpalette([0, 0, 0] + [9, 9, 9] * 255)
    for x in range(1, 5):
        im.putpixel((x, 3), 12)
    p = tmp_path / "idx.png"
    im.save(p)
    SI.import_images(kfm, [p], 7400, 0, SI.ImportOptions(mode="swap", palette=(1, 1), autocrop=False))
    spr = s.find(7400, 0)
    assert spr.palette_index == s.find_palette(1, 1) and set(s.pixels(spr)) == {0, 12}
    # invertida: a última cor vira a 0 (o fundo)
    rev = SI.reverse_palette(im)
    assert np.asarray(rev)[0, 0] == 255 and rev.getpalette()[:3] == [9, 9, 9]
    # paleta igual que já existe é reaproveitada; sprite igual vira link
    f = _figure(tmp_path, "x.png")
    r1 = SI.import_images(kfm, [f], 7401, 0, SI.ImportOptions(mode="own"))
    r2 = SI.import_images(kfm, [f], 7401, 1, SI.ImportOptions(mode="own"))
    assert r1["palettes"] and not r2["palettes"]
    assert s.find(7401, 1).palette_index == s.find(7401, 0).palette_index
    assert r2["linked"] == [[7401, 1, 7401, 0]] and s.find(7401, 1).linked_to == s.index_of(7401, 0)
    r3 = SI.import_images(kfm, [f], 7401, 2, SI.ImportOptions(mode="own", share=False))
    assert not r3["linked"] and s.find(7401, 2).linked_to is None
    with pytest.raises(ValueError):                       # trocar exige imagem indexada
        SI.convert(SI.open_images([f]), kfm, SI.ImportOptions(mode="swap", palette=(1, 1)))
