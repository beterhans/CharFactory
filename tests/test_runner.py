"""Rodar no motor: MUGEN ou Ikemen GO, a pasta escolhida e o log de cada um (sem abrir o motor)."""
import os
import platform
import sys
import time

import pytest

from charfactory import project
from charfactory.tools import generate, runner


def _engine(root, exe):
    (root / "chars").mkdir(parents=True)
    (root / "data").mkdir()
    (root / exe).write_bytes(b"")
    return root


def _app(root, name="I.K.E.M.E.N-Go_arm.app", exe_name="Ikemen_GO_MacOSARM"):
    """Bundle .app falso do Ikemen GO (o layout que o launcher oficial usa no macOS)."""
    macos = root / name / "Contents" / "MacOS"
    macos.mkdir(parents=True)
    exe = macos / exe_name
    exe.write_bytes(b"")
    os.chmod(exe, 0o755)
    (macos / "bundle_run.sh").write_text("#!/bin/sh\n", "utf-8")
    return root / name


def _char(root, name="Teste", zss=False):
    c = project.load(generate.new_character(root / "chars" / name, name))
    if zss:
        (c.dir / f"{name}.zss").write_text("[StateDef 0;]\n", "utf-8")
        text = c.def_path.read_text("utf-8").replace(f"st = {name}.cns", f"st = {name}.zss")
        c.def_path.write_text(text, "utf-8")
        c = project.load(c.def_path)
    return c


def test_detects_the_engine_of_a_folder(tmp_path):
    mugen = _engine(tmp_path / "mugen", "MUGEN-ORIGINAL.exe")
    ikemen = _engine(tmp_path / "ikemen", "Ikemen_GO.exe")
    (ikemen / "Ikemen_GO_prev.exe").write_bytes(b"")
    assert not runner.is_ikemen(mugen) and runner.is_ikemen(ikemen)
    assert runner.engine_exe(mugen) == (mugen / "MUGEN-ORIGINAL.exe", "mugen")
    assert runner.engine_exe(ikemen) == (ikemen / "Ikemen_GO.exe", "ikemen")
    with pytest.raises(FileNotFoundError):
        runner.find_ikemen_exe(mugen)


def test_auto_runs_in_the_folder_the_character_is_in(tmp_path):
    mugen = _engine(tmp_path / "mugen", "mugen.exe")
    ikemen = _engine(tmp_path / "ikemen", "Ikemen_GO.exe")
    in_ikemen = _char(ikemen)
    assert runner.engine_root(in_ikemen, "auto", mugen, None) == (ikemen, "ikemen")
    assert runner.char_argument(in_ikemen, ikemen) == "Teste/Teste.def"
    in_mugen = _char(mugen)
    assert runner.engine_root(in_mugen, "auto", None, ikemen) == (mugen, "mugen")
    # forçado no menu: o outro motor, pela pasta das Opções
    assert runner.engine_root(in_mugen, "ikemen", mugen, ikemen) == (ikemen, "ikemen")
    assert runner.engine_root(in_ikemen, "mugen", mugen, ikemen) == (mugen, "mugen")


def test_auto_outside_an_engine_sends_zss_to_ikemen(tmp_path):
    mugen = _engine(tmp_path / "mugen", "mugen.exe")
    ikemen = _engine(tmp_path / "ikemen", "Ikemen_GO.exe")
    loose = tmp_path / "work"
    cns_char, zss_char = _char(loose, "Cns"), _char(loose, "Zss", zss=True)
    assert zss_char.is_zss and not cns_char.is_zss
    assert runner.engine_root(cns_char, "auto", mugen, ikemen) == (mugen, "mugen")
    assert runner.engine_root(zss_char, "auto", mugen, ikemen) == (ikemen, "ikemen")
    # só o Ikemen configurado (ou a "pasta do MUGEN" é um Ikemen): vai para ele
    assert runner.engine_root(cns_char, "auto", ikemen, None) == (ikemen, "ikemen")
    with pytest.raises(ValueError):
        runner.engine_root(cns_char, "outro")


def test_command_line_is_the_same_for_both_engines(tmp_path):
    exe = tmp_path / "Ikemen_GO.exe"
    assert runner.engine_args(exe, "kfm/kfm.def") == [str(exe), "kfm/kfm.def", "kfm/kfm.def"]
    assert runner.engine_args(exe, "a/a.def", "kfm", "stage0.def", p2_ai=8, rounds=1)[1:] == \
        ["a/a.def", "kfm", "-s", "stage0.def", "-p2.ai", "8", "-rounds", "1"]


def test_reads_only_the_log_written_by_this_run(tmp_path):
    mugen = _engine(tmp_path / "mugen", "mugen.exe")
    ikemen = _engine(tmp_path / "ikemen", "Ikemen_GO.exe")
    old = mugen / "mugen.log"
    old.write_text("old", "cp1252")
    os.utime(old, (time.time() - 100, time.time() - 100))
    since = time.time() - 10
    assert runner.engine_log(mugen, "mugen", since) is None
    logs = ikemen / "save" / "logs"
    logs.mkdir(parents=True)
    (logs / "Ikemen_2026-10-21_10-00-00.log").write_text("Error: char not found", "utf-8")
    assert "char not found" in runner.engine_log(ikemen, "ikemen", since)
    assert runner.engine_log(ikemen, "mugen", since) is None


def test_ikemen_loads_a_character_outside_chars_by_its_full_path(tmp_path):
    mugen = _engine(tmp_path / "mugen", "mugen.exe")
    ikemen = _engine(tmp_path / "ikemen", "Ikemen_GO.exe")
    c = _char(mugen)
    assert runner.char_argument(c, ikemen, "ikemen") == c.def_path.as_posix()
    with pytest.raises(ValueError):
        runner.char_argument(c, ikemen)            # o MUGEN só carrega de dentro de chars/


def test_warns_about_a_motif_that_does_not_exist(tmp_path):
    ikemen = _engine(tmp_path / "ikemen", "Ikemen_GO.exe")
    (ikemen / "save").mkdir()
    cfg = ikemen / "save" / "config.ini"
    cfg.write_text("[Config]\nMotif             = data/ikemen1/system.def\n", "utf-8")
    assert "data/ikemen1/system.def" in runner.config_problem(ikemen, "ikemen")
    (ikemen / "data" / "ikemen1").mkdir()
    (ikemen / "data" / "ikemen1" / "system.def").write_text("", "utf-8")
    assert runner.config_problem(ikemen, "ikemen") is None
    assert runner.config_problem(ikemen, "mugen") is None


def test_an_ikemen_app_bundle_marks_the_folder(tmp_path):
    root = tmp_path / "ikemen"
    (root / "chars").mkdir(parents=True)
    _app(root, "I.K.E.M.E.N-Go.app")          # só o bundle: sem .exe e sem main.lua
    assert runner.is_ikemen(root)


@pytest.mark.skipif(sys.platform != "darwin", reason="bundle .app é do macOS")
def test_finds_the_executable_inside_an_ikemen_app_bundle(tmp_path):
    root = _engine(tmp_path / "ikemen", "Ikemen_GO.exe")   # a pasta tem o .exe e os bundles
    arm = _app(root, "I.K.E.M.E.N-Go_arm.app", "Ikemen_GO_MacOSARM")
    intel = _app(root, "I.K.E.M.E.N-Go_Intel.app", "Ikemen_GO_MacOS")
    if platform.machine() == "arm64":
        want = arm / "Contents" / "MacOS" / "Ikemen_GO_MacOSARM"
    else:
        want = intel / "Contents" / "MacOS" / "Ikemen_GO_MacOS"
    assert runner.find_ikemen_exe(root) == want      # o .app ganha do .exe no macOS
    assert runner.engine_exe(root) == (want, "ikemen")
    # escolhido nas Opções: não adivinha pela arquitetura, usa o bundle pedido
    assert runner.find_ikemen_exe(root, intel) == intel / "Contents" / "MacOS" / "Ikemen_GO_MacOS"
    assert runner.engine_exe(root, intel) == (intel / "Contents" / "MacOS" / "Ikemen_GO_MacOS", "ikemen")


def test_pointing_at_the_app_bundle_uses_the_folder_that_contains_it(tmp_path):
    root = _engine(tmp_path / "ikemen", "Ikemen_GO.exe")
    app = _app(root)
    c = _char(root)
    assert runner.engine_root(c, "ikemen", None, app) == (root, "ikemen")
    assert runner.char_argument(c, root) == "Teste/Teste.def"


def test_chosen_app_only_applies_to_its_own_folder(tmp_path):
    root = _engine(tmp_path / "ikemen", "Ikemen_GO.exe")
    app = _app(root)
    assert runner.chosen_app(root, app) == app
    assert runner.chosen_app(tmp_path / "outro", app) is None   # outra pasta: não vale
    assert runner.chosen_app(root, root) is None                # pasta comum não é bundle
    assert runner.chosen_app(None, app) is None


def test_prepare_engine_is_a_noop_without_quarantine(tmp_path):
    root = _engine(tmp_path / "ikemen", "Ikemen_GO.exe")
    app = _app(root)
    runner.prepare_engine(app / "Contents" / "MacOS" / "Ikemen_GO_MacOSARM")   # não quebra
