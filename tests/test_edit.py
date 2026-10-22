import shutil

import pytest

from charfactory import project
from charfactory.formats import mtext
from charfactory.tools import edit, render


@pytest.fixture()
def kfm(mugen_dir, tmp_path):
    work = tmp_path / "chars" / "kfm"
    shutil.copytree(mugen_dir / "chars" / "kfm", work)
    return project.load(work / "kfm.def")


def _rgba(c, g, i, pal=None):
    return render.sprite_image(c, g, i, pal).tobytes()


def test_sort_palette_keeps_images(kfm):
    before = _rgba(kfm, 0, 0)
    r = edit.sort_palette_by_tones(kfm, 1)
    assert r["sprites_remapped"] > 100
    assert _rgba(kfm, 0, 0) == before


def test_swap_colors_keeps_images(kfm):
    before = _rgba(kfm, 200, 1)
    edit.swap_palette_colors(kfm, 1, 3, 7)
    assert _rgba(kfm, 200, 1) == before


def test_alternate_palettes_follow_the_shared_pixels(kfm):
    """As paletas 1,2+ pintam os mesmos índices dos sprites da 1,1: limpar cores sem uso na 1,2
    apagava a paleta inteira, e trocar/ordenar a 1,1 deixava a 1,2 com as cores fora do lugar."""
    used = edit.used_palette_indices(kfm, 1)
    assert edit.used_palette_indices(kfm, 2) == used
    before2 = _rgba(kfm, 0, 0, 2)
    edit.clear_unused_colors(kfm, 2)
    assert _rgba(kfm, 0, 0, 2) == before2
    a, b = sorted(used - {0})[:2]
    edit.swap_palette_colors(kfm, 1, a, b)
    assert _rgba(kfm, 0, 0, 2) == before2
    edit.sort_palette_by_tones(kfm, 1)
    assert _rgba(kfm, 0, 0, 2) == before2


def test_own_palette_by_group_and_item(kfm):
    k = kfm.sprites.find_palette(9000, 1)
    edit.set_palette_colors(kfm, (9000, 1), {"5": "#102030"})
    assert kfm.sprites.palettes[k].colors[5] == (16, 32, 48)
    with pytest.raises(ValueError):
        edit.set_palette_colors(kfm, (3, 99), {"5": "#102030"})


def test_palette_color_effects(kfm):
    """Efeitos como os do FF: azul vira vermelho só nos tons azuis; trocas de canal; e uma
    paleta repetida (mesmo grupo,índice) é editada pela posição, sem mexer na outra."""
    from charfactory.formats import sff
    s = kfm.sprites
    s.palettes.append(sff.Palette(3, 9, [(0, 0, 0), (40, 60, 220), (230, 190, 150), (128, 128, 128)]))
    s.palettes.append(sff.Palette(3, 9, [(0, 0, 0), (40, 60, 220), (230, 190, 150), (128, 128, 128)]))
    k = len(s.palettes) - 1
    r = edit.recolor_family(kfm, (3, 9, k), "blue", "red")
    cols = s.palettes[k].colors
    assert r["changed"] == 1 and cols[1][0] > 150 and cols[1][2] < 100      # azul -> vermelho
    assert cols[2] == (230, 190, 150) and cols[3] == (128, 128, 128)        # pele e cinza ficam
    assert s.palettes[k - 1].colors[1] == (40, 60, 220)                     # a outra 3,9 não muda
    edit.palette_effect(kfm, (3, 9, k), "swap_rb", [2, 3])
    assert cols[2] == (150, 190, 230) and cols[0] == (0, 0, 0)
    edit.palette_effect(kfm, (3, 9, k), "rotate_rgb", [3])
    assert cols[3] == (128, 128, 128)
    with pytest.raises(ValueError):
        edit.palette_effect(kfm, 1, "blur")


def test_gradient_endpoints(kfm):
    edit.palette_gradient(kfm, 1, 10, 20, "#000000", "#ffffff")
    p = kfm.sprites.palettes[kfm.sprites.find_palette(1, 1)].colors
    assert p[10] == (0, 0, 0) and p[20] == (255, 255, 255) and p[15] == (128, 128, 128)


def test_transforms_roundtrip(kfm):
    s = kfm.sprites.find(0, 0)
    before = (_rgba(kfm, 0, 0), s.axis_x, s.axis_y)
    edit.transform_sprite(kfm, 0, 0, flip_h=True)
    edit.transform_sprite(kfm, 0, 0, flip_h=True)
    edit.transform_sprite(kfm, 0, 0, rotate=90)
    edit.transform_sprite(kfm, 0, 0, rotate=270)
    s = kfm.sprites.find(0, 0)
    assert (_rgba(kfm, 0, 0), s.axis_x, s.axis_y) == before


def test_renumber_group_updates_animations(kfm):
    edit.renumber_group(kfm, 200, 7200)
    assert kfm.sprites.find(200, 0) is None and kfm.sprites.find(7200, 0) is not None
    assert all(f.group != 200 for a in kfm.anims.actions.values() for f in a.frames)
    kfm.save()
    from charfactory import validate
    errs = [i for i in validate.validate_character(project.load(kfm.def_path)) if "não existe em" in i.message]
    assert errs == []


def test_optimize_and_set_all(kfm):
    from charfactory.formats import air
    kfm.anims.set_action(air.parse_action(9300, ["0,0, 0,0, 3", "0,0, 0,0, 4", "0,1, 0,0, 2"]))
    r = edit.optimize_action(kfm, 9300)
    assert r["removed_frames"] == 1 and kfm.anims.get(9300).frames[0].time == 7
    edit.set_all_frames(kfm, 9300, time=5, offset_dx=2)
    assert {f.time for f in kfm.anims.get(9300).frames} == {5}


def test_apply_clsn_all_instances(kfm):
    r = edit.apply_clsn_to_sprite(kfm, 0, 0, clsn2=[[-10, 0, 10, -80]])
    assert r["frames_updated"] >= 1


def test_edit_sound(kfm):
    s = kfm.sounds.sounds[0]
    rate = s.info()["rate"]
    r = edit.edit_sound(kfm, s.group, s.number, volume=0.5, fade_out_ms=20, resample_hz=rate * 2)
    assert r["rate"] == rate * 2


def test_format_cns_idempotent(mugen_dir):
    text, _ = mtext.read_text(mugen_dir / "chars/kfm/kfm.cns")
    once = edit.format_cns(text)
    assert edit.format_cns(once) == once
    # a formatação não muda o significado
    a, b = mtext.parse(text), mtext.parse(once)
    assert [(s.name, s.as_dict()) for s in a.sections] == [(s.name, s.as_dict()) for s in b.sections]


def test_text_file_tools_on_stage(mugen_dir, tmp_path):
    if not (mugen_dir / "stages/stage0.def").exists():
        pytest.skip("stage0.def é da instalação oficial do MUGEN 1.0")
    st = tmp_path / "stage0.def"
    shutil.copy(mugen_dir / "stages/stage0.def", st)
    secs = edit.text_sections(str(st))
    assert any(s["name"].lower() == "camera" for s in secs)
    edit.text_set_value(str(st), "Camera", "boundleft", "-200")
    assert mtext.load(st).get("camera", "boundleft") == "-200"
