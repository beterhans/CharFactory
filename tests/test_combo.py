"""Golpe em passos (build_move): os passos viram estados encadeados que acertam no simulador,
refazer substitui os estados do próprio golpe, e erros voltam para o modelo com a saída."""
import json
import re

import pytest

from charfactory.ai import tools
from charfactory.tools import combo

RISING = [{"role": "strike", "anim": 200}, {"role": "strike", "anim": 210}, {"role": "launcher", "anim": 410},
          {"role": "air_strike", "anim": 610}, {"role": "air_finisher", "anim": 640}]


@pytest.fixture()
def kfm(mugen_dir):
    h = tools.Host()
    h.open_character(str(mugen_dir / "chars" / "kfm" / "kfm.def"))
    return h


def _build(host, **args):
    r = tools.run(host, "build_move", args)
    assert not r.is_error, r.text
    return json.loads(r.text)


def test_punches_launcher_and_air_attack_all_connect(kfm):
    out = _build(kfm, steps=RISING, command="~D, DF, F, z", name="Rising Combo")
    assert out["verdict"].startswith("every hit connects")
    roles = [s["role"] for s in out["steps"]]
    assert roles == ["strike", "strike", "launcher", "jump", "air_strike", "air_finisher"]   # o pulo entra sozinho
    assert all(s["hit"].startswith("tick") for s in out["steps"] if s["role"] != "jump")
    assert 50 in out["connects_from_distances"]
    first = out["states"][0]
    text = tools.run(kfm, "get_state", {"number": first + 2}).text
    assert "fall = 1" in text and "next step if it hit" in text and combo.MARK in text
    assert tools.run(kfm, "validate_character", {"number": first}).text.startswith('{"errors":0')
    r = json.loads(tools.run(kfm, "test_command", {"command": out["command"]}).text)
    assert r["state"] == first


def test_doing_it_again_replaces_its_own_states(kfm):
    first = _build(kfm, steps=RISING, command="~D, DF, F, z")["states"][0]
    out = _build(kfm, steps=RISING[:2], command="~D, DF, F, z", state=first)
    assert out["states"] == [first, first + 1]
    assert first + 2 not in kfm.char.all_statedefs()                     # o resto da versão antiga sai
    minus1 = kfm.char.all_statedefs()[-1][0]
    assert sum(1 for c in minus1.controllers if (c.section.get("value") or "").strip() == str(first)) == 1


def test_an_animation_without_attack_box_gets_a_copy_with_one(kfm):
    out = _build(kfm, steps=[{"role": "strike", "anim": 200}, {"role": "finisher", "anim": 195}],
                 command="~D, DF, F, z")
    step = out["steps"][1]
    assert step["anim"] != 195 and "no attack box" in step["note"]
    assert kfm.char.anims.get(step["anim"]).frames and not any(f.clsn1 for f in kfm.char.anims.get(195).frames)


def test_mistakes_come_back_to_the_model_without_changes(kfm):
    before = set(kfm.char.all_statedefs())
    r = tools.run(kfm, "build_move", {"steps": [{"role": "kick", "anim": 200}], "command": "z"})
    assert r.is_error and "strike" in r.text
    r = tools.run(kfm, "build_move", {"steps": RISING, "command": "~D, DF, F, x"})
    assert r.is_error and "Kung Fu Palm" in r.text and "free inputs" in r.text
    r = tools.run(kfm, "build_move", {"steps": RISING, "command": "~D, DF, F, z", "state": 1000})
    assert r.is_error and "belongs to another move" in r.text
    assert set(kfm.char.all_statedefs()) == before


def test_the_move_uses_the_characters_own_sparks_and_sounds(kfm):
    # um char no estilo JUS: todos os golpes com sons próprios e a faísca feita por um Explod
    for n in (200, 210, 230, 240, 400, 410, 430, 440, 600, 610, 630, 640):
        text = tools.run(kfm, "get_state", {"number": n}).text
        text = re.sub(r"(?im)^(\s*sparkno\s*=).*$", r"\1 -1", text)
        text = re.sub(r"(?im)^(\s*hitsound\s*=).*$", r"\1 S1,16", text)
        text += ("\n[State 200, my spark]\ntype = Explod\ntrigger1 = MoveHit = 1\nanim = 7010\npostype = p2\n"
                 "removetime = -2\nownpal = 1\n")
        assert not tools.run(kfm, "set_state", {"number": n, "text": text, "replace": True}).is_error
    first = _build(kfm, steps=RISING[:2], command="~D, DF, F, z")["states"][0]
    out = tools.run(kfm, "get_state", {"number": first}).text
    assert "sparkno = -1" in out and "hitsound = S1,16" in out
    assert "type = Explod" in out and "anim = 7010" in out and "persistent = 0" in out


def test_only_the_last_hit_of_a_launcher_launches(kfm):
    frames = [{"group": 210, "item": 0, "time": 4}, {"group": 210, "item": 3, "time": 4, "attack": True},
              {"group": 210, "item": 5, "time": 4}, {"group": 210, "item": 3, "time": 4, "attack": True},
              {"group": 210, "item": 5, "time": 6}]
    assert not tools.run(kfm, "build_animation", {"number": 1460, "frames": frames}).is_error
    first = _build(kfm, steps=[{"role": "strike", "anim": 200}, {"role": "launcher", "anim": 1460}],
                   command="~D, DF, F, z")["states"][0]
    hits = re.split(r"(?m)^\[State \d+, hit \d+\]", tools.run(kfm, "get_state", {"number": first + 1}).text)[1:]
    assert len(hits) == 2 and "fall = 1" not in hits[0].split("[State")[0] and "fall = 1" in hits[1]
