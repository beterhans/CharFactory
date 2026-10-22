"""Funções de produtividade: ir para a definição, paleta de comandos, recursos não usados."""
import os
import shutil

import pytest

from charfactory import project
from charfactory.tools import usage

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from charfactory.gui.dialogs import fuzzy_score  # noqa: E402
from charfactory.gui.editors.code import reference_at, reference_doc  # noqa: E402

CNS = """[Statedef 200, soco]
type = S
anim = 200

[State 200, som]
type = PlaySnd
trigger1 = Time = 2
value = 5, 0

[State 200, fim]
type = ChangeState
trigger1 = AnimTime = 0
value = 0

[State 200, golpe]
type = HitDef
trigger1 = 1
hitsound = S1, 2
guardsound = 6, 0
p2stateno = 820

[State 200, calc]
type = ChangeAnim
trigger1 = 1
value = 200 + var(1)
""".split("\n")


def _line(text):
    return next(i for i, ln in enumerate(CNS) if ln.startswith(text))


def test_reference_at():
    assert reference_at(CNS, 0) == ("state", 200, 0)
    assert reference_at(CNS, _line("anim =")) == ("anim", 200, 0)
    assert reference_at(CNS, _line("value = 5, 0")) == ("sound", 5, 0)
    assert reference_at(CNS, _line("value = 0")) == ("state", 0, 0)
    assert reference_at(CNS, _line("hitsound")) == ("sound", 1, 2)
    assert reference_at(CNS, _line("guardsound")) is None  # sem S: som comum do fightfx
    assert reference_at(CNS, _line("p2stateno")) == ("state", 820, 0)
    assert reference_at(CNS, _line("value = 200 + var")) is None  # expressão: não dá para resolver
    assert reference_at(CNS, _line("trigger1 = Time")) is None


def test_reference_doc():
    assert "HitDef" in reference_doc("hitdef") and "controller" in reference_doc("HitDef")
    assert "trigger" in reference_doc("AnimTime")
    assert reference_doc("banana") is None


def test_fuzzy_score():
    assert fuzzy_score("", "qualquer") == 0
    assert fuzzy_score("anim 20", "anim 20 · Walking") > fuzzy_score("anim 20", "anim 200 · Punch")
    assert fuzzy_score("slv", "Projeto › Salvar") is not None
    assert fuzzy_score("xyz", "Projeto › Salvar") is None


@pytest.fixture()
def kfm(mugen_dir, tmp_path):
    work = tmp_path / "chars" / "kfm"
    shutil.copytree(mugen_dir / "chars" / "kfm", work)
    (tmp_path / "data").mkdir()
    shutil.copy(mugen_dir / "data" / "common1.cns", tmp_path / "data")
    return project.load(work / "kfm.def")


def test_unused_resources(kfm):
    r = usage.unused_resources(kfm)
    assert all(g != usage.PORTRAIT_GROUP for g, _ in r["sprites"])
    used = {(f.group, f.item) for a in kfm.anims.actions.values() for f in a.frames}
    assert not any(tuple(s) in used for s in r["sprites"])
    assert r["dynamic_references"] > 0  # o common1 calcula animações de tomar golpe
    # uma animação nova sem nenhuma referência aparece; referenciada por ChangeAnim some
    from charfactory.tools import ops
    ops.create_action(kfm, 7777, [{"group": 0, "item": 0, "time": 5}])
    assert 7777 in usage.unused_resources(kfm)["animations"]
    ops.add_controller(kfm, 200, "[State 200, t]\ntype = ChangeAnim\ntrigger1 = 0\nvalue = 7777\n")
    assert 7777 not in usage.unused_resources(kfm)["animations"]


def test_unused_resources_without_false_positives(kfm):
    """Referências que antes passavam despercebidas e faziam um recurso usado aparecer na lista."""
    from charfactory.tools import edit, ops
    g, n = kfm.sounds.sounds[0].group, kfm.sounds.sounds[0].number
    for new in [(900, 0), (901, 0), (901, 1), (901, 2), (902, 5)]:
        edit.duplicate_sound(kfm, g, n, *new)
    for a in (7700, 7701, 7702, 7710, 7800, 7850, 7990):
        ops.create_action(kfm, a, [{"group": 0, "item": 0, "time": 5}])
    code = ("[State 200, a]\ntype = Explod\ntrigger1 = 0\nanim = 7700 + (random % 3)\n"
            "[State 200, b]\ntype = HitDef\ntrigger1 = 0\nsparkno = S7710\nguard.sparkno = 7711\n"
            "[State 200, c]\ntype = ChangeAnim\ntrigger1 = 0\nvalue = 7800 + var(3)\n"
            "[State 200, d]\ntype = PlaySnd\ntrigger1 = 0\nvalue = S900, 0\n"
            "[State 200, e]\ntype = PlaySnd\ntrigger1 = 0\nvalue = 901, random%3\n"
            "[State 200, f]\ntype = PlaySnd\ntrigger1 = 0\nvalue = S902, var(2)\n")
    for block in code.split("[State")[1:]:
        ops.add_controller(kfm, 200, "[State" + block)
    r = usage.unused_resources(kfm)
    assert not {7700, 7701, 7702, 7710} & set(r["animations"])        # random%3 e faísca própria (S)
    assert {7850} <= set(r["maybe_animations"]) and 7850 not in r["animations"]   # 7800 + var(3)
    assert 7990 in r["animations"]                                        # longe de qualquer base
    sounds = {tuple(s) for s in r["sounds"]}
    assert not {(900, 0), (901, 0), (901, 1), (901, 2), (11, 0)} & sounds   # S900,0, random e KO
    assert [902, 5] in r["maybe_sounds"] and (902, 5) not in sounds          # número calculado
    assert all(not 5000 <= s[0] < 6000 for s in r["sprites"])                # tomar golpe (arremessos)


def test_timeline_drag_rewrites_animelem_and_not_time(kfm):
    """Arrastar na linha do tempo do Simulador: antes só `trigger1 = Time = N` aceitava, e a
    maioria dos sons e efeitos dispara por AnimElem ou !Time."""
    from charfactory.tools import movetimeline as M, ops, simulate
    sim = simulate.simulate(kfm, 1100, max_ticks=200)
    it = next(x for x in M.build(sim)["rows"]["sons"] if not x.get("hitsound") and x.get("ci") is not None)
    ctrl, _ = M.controller(kfm, 1100, it["ci"])
    assert M.timing_trigger(ctrl)["kind"] == "elem"
    to = it["i0"] + 4
    r = M.move_event(kfm, sim, it, to)
    assert r["new"].startswith("AnimElem") and not r["note"]
    sim = simulate.simulate(kfm, 1100, max_ticks=200)
    assert to in [x["i0"] for x in M.build(sim)["rows"]["sons"] if x.get("ci") == it["ci"]]

    ops.add_controller(kfm, 1100, "[State 1100, novo]\ntype = PlaySnd\ntriggerall = var(30) = 0\n"
                                  "trigger1 = !Time ; no começo\nvalue = 0,0\n")
    ops.add_controller(kfm, 1100, "[State 1100, preso]\ntype = PlaySnd\ntriggerall = time > 2\n"
                                  "trigger1 = AnimElem = 2\nvalue = 0,0\n")
    sd = kfm.all_statedefs()[1100][0]
    novo, preso = len(sd.controllers) - 2, len(sd.controllers) - 1
    assert M.timing_trigger(sd.controllers[preso]) is None      # o triggerall também fala de tempo
    sim = simulate.simulate(kfm, 1100, max_ticks=200)
    it = next(x for x in M.build(sim)["rows"]["sons"] if x.get("ci") == novo)
    r = M.move_event(kfm, sim, it, it["i0"] + 2)
    assert (r["old"], r["new"]) == ("!Time", "Time = 2")
    assert "trigger1 = Time = 2 ; no começo" in sd.controllers[novo].section.lines   # o comentário fica


def test_simulator_sparks_end_helpers_use_their_size_and_hidden_helpers_stay_off_camera(kfm):
    """Bugs do Simulador vistos no Jotaro: faísca com quadro de tempo 0 no fim nunca saía (e o
    helper que espera !NumExplod ficava na tela), o const(size.xscale) do helper era o do char
    (faísca 2,5× maior) e um helper invisível parado em 999,999 encolhia tudo num canto."""
    from charfactory.tools import ops, simulate
    ops.create_action(kfm, 7790, [{"group": 0, "item": 0, "time": 5}, {"group": 0, "item": 0, "time": 0}])
    ops.add_controller(kfm, 200, "[State 200, faisca]\ntype = Explod\ntrigger1 = Time = 0\nanim = 7790\n"
                                 "removetime = -2\n")
    sim = simulate.simulate(kfm, 200, max_ticks=120)
    alive = [i for i, r in enumerate(sim.track) if any(x["anim"] == 7790 for x in r["explods"])]
    assert alive and max(alive) < 10 and not any(e.alive and e.anim == 7790 for e in sim.explods)

    p1 = sim.p1
    base = p1.const("size.xscale")
    p1.size = {"size.xscale": [0.4], "size.head.pos": [3.0, -50.0]}
    assert p1.const("size.xscale") == 0.4 and p1.const("size.head.pos.y") == -50.0
    assert p1.const("size.height") == sim.const("size.height")      # o resto vem do char
    p1.size = {}
    assert p1.const("size.xscale") == base

    w = simulate._window(sim)
    sim.track[3]["ents"].append(dict(sim.track[3]["ents"][0], name="helper 9", pos=(999, 999), frame=None))
    assert simulate._window(sim) == w


def test_blend_reads_trans_alpha_and_air():
    from charfactory.tools.simulate import _blend
    f = lambda t: type("F", (), {"trans": t})()
    assert _blend(f(""), None, None) == ("normal", 1.0, 1.0)
    assert _blend(f("A"), None, None) == ("add", 1.0, 1.0)
    assert _blend(f("A1"), None, None) == ("add", 1.0, 0.5)
    assert _blend(f("Sub"), None, None)[0] == _blend(f("S"), None, None)[0] == "sub"
    assert _blend(f("AS256D0"), None, None) == ("normal", 1.0, 1.0)  # fonte cheia, fundo zero: opaco
    assert _blend(f("AS128D128"), None, None) == ("add", 0.5, 0.5)
    assert _blend(f("A"), "none", None)[0] == "normal"               # o Trans manda no AIR
    assert _blend(f(""), "sub", None)[0] == "sub"
    assert _blend(f(""), "addalpha", (110, 256)) == ("add", 110 / 256, 1.0)


def test_helper_states_group():
    from charfactory.formats import cns, mtext
    st = cns.States(mtext.parse(
        "[Statedef 200]\n[State 200, h]\ntype = Helper\ntrigger1 = 1\nstateno = 9000\n"
        "[State 200, c]\ntype = ChangeState\ntrigger1 = 1\nvalue = 210\n"
        "[Statedef 210]\n[State 210, c]\ntype = ChangeState\ntrigger1 = 1\nvalue = 0\n"
        "[Statedef 9000]\n[State 9000, c]\ntype = ChangeState\ntrigger1 = 1\nvalue = 9001\n"
        "[Statedef 9001]\n[State 9001, c]\ntype = ChangeState\ntrigger1 = 1\nvalue = 210\n"
        "[Statedef 0]\n"))
    # 9000 é alvo de Helper e leva ao 9001; o 210 o char também usa, então fica do char
    assert usage.helper_states(st.statedefs) == {9000, 9001}
