"""Executa o MUGEN ou o Ikemen GO com um personagem."""
from __future__ import annotations

import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

from ..project import Character, find_mugen_root
from ..i18n import tr

ENGINES = ("auto", "mugen", "ikemen")
ENGINE_NAMES = {"mugen": "MUGEN", "ikemen": "Ikemen GO"}


def _name_key(name: str) -> str:
    """Nome sem pontuação, para casar 'I.K.E.M.E.N-Go_arm.app' com 'ikemen'."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def is_app_bundle(p: str | Path) -> bool:
    """Bundle .app do macOS (uma pasta com Contents/)."""
    p = Path(p)
    return p.suffix == ".app" and (p / "Contents").is_dir()


def _ikemen_app(root: str | Path) -> Path | None:
    """Bundle .app do Ikemen GO na pasta (ou a própria pasta, se for um bundle). No Apple
    Silicon prefere o *_arm.app; no Intel, o *_Intel.app."""
    root = Path(root)
    if is_app_bundle(root):
        return root
    apps = [p for p in sorted(root.glob("*.app")) if "ikemen" in _name_key(p.name)]
    if not apps:
        return None
    want = "arm" if platform.machine() == "arm64" else "intel"

    def score(p: Path) -> int:
        k = _name_key(p.name)
        if want in k:
            return 0
        other = "intel" if want == "arm" else "arm"
        return 2 if other in k else 1      # 1 = genérico/universal

    return sorted(apps, key=score)[0]


def _mac_app_exe(app: Path) -> Path:
    """O executável do bundle (Contents/MacOS/...), pulando os scripts .sh."""
    macos = app / "Contents" / "MacOS"
    exes = [p for p in sorted(macos.iterdir()) if p.is_file() and p.suffix != ".sh"
            and os.access(p, os.X_OK)]
    if not exes:
        raise FileNotFoundError(tr("no executable in {0}").format(macos))
    if platform.machine() == "arm64":
        arm = [p for p in exes if "arm" in _name_key(p.name)]
        if arm:
            return arm[0]
    return exes[0]


def prepare_engine(exe: str | Path) -> None:
    """macOS: bundle baixado vem com 'quarentena' e o sistema barra a execução; remove o
    atributo (o launcher oficial do Ikemen faz o mesmo)."""
    if sys.platform != "darwin":
        return
    app = next((q for q in [Path(exe), *Path(exe).parents] if is_app_bundle(q)), None)
    if not app:
        return
    try:
        has = subprocess.run(["xattr", "-p", "com.apple.quarantine", str(app)],
                             capture_output=True).returncode == 0
        if has:
            subprocess.run(["xattr", "-rd", "com.apple.quarantine", str(app)], capture_output=True)
    except OSError:
        pass


def char_argument(char: Character, mugen_root: Path, engine: str = "mugen") -> str:
    """Caminho que o motor espera: relativo a chars/ (ex.: 'kfm/kfm.def'); fora de chars/, o
    Ikemen GO carrega o .def pelo caminho completo e o MUGEN não carrega."""
    chars = (mugen_root / "chars").resolve()
    try:
        rel = char.def_path.relative_to(chars)
    except ValueError:
        if engine == "ikemen":
            return char.def_path.as_posix()
        raise ValueError(tr("the character must be inside {0} for the engine to load it").format(chars))
    return rel.as_posix()


def config_problem(root: Path, engine: str) -> str | None:
    """O que faz a luta rápida fechar antes de carregar o personagem: no Ikemen GO, um Motif em
    save/config.ini que não existe (sem ele não há fight.def)."""
    if engine != "ikemen":
        return None
    try:
        text = (root / "save" / "config.ini").read_text("utf-8", errors="replace")
    except OSError:
        return None
    m = re.search(r"(?im)^\s*Motif\s*=\s*(.+?)\s*$", text)
    if m and not (root / m[1].strip('"')).exists():
        return tr("save/config.ini: Motif = {0} does not exist; Ikemen GO closes without its fight.def").format(m[1])
    return None


def is_ikemen(root: str | Path) -> bool:
    """Pasta do Ikemen GO: tem o Ikemen_GO.exe, os scripts dele (external/script/main.lua)
    ou um bundle .app do Ikemen (macOS, ex.: I.K.E.M.E.N-Go_arm.app)."""
    root = Path(root)
    return any("ikemen" in _name_key(p.name) for p in root.glob("*.exe")) or \
        (root / "external" / "script" / "main.lua").exists() or \
        any("ikemen" in _name_key(p.name) for p in root.glob("*.app"))


def find_ikemen_exe(root: str | Path, app: str | Path | None = None) -> Path:
    """Ikemen_GO.exe ou outro nome com 'ikemen' (ex.: Ikemen_GO_x64.exe); no macOS, o
    executável do bundle .app escolhido (ou, sem escolha, o da arquitetura)."""
    if sys.platform == "darwin":
        bundle = Path(app) if (app and is_app_bundle(app)) else _ikemen_app(root)
        if bundle:
            return _mac_app_exe(bundle)
    exes = [p for p in Path(root).glob("*.exe") if "ikemen" in _name_key(p.name)
            and not any(k in p.name.lower() for k in ("setup", "unins", "prev"))]
    if not exes:
        raise FileNotFoundError(tr("no Ikemen GO executable in {0}").format(root))
    return sorted(exes, key=lambda p: len(p.name))[0]


def engine_exe(root: str | Path, app: str | Path | None = None) -> tuple[Path, str]:
    """(executável, 'mugen' ou 'ikemen') da pasta do motor; `app` é o bundle .app escolhido
    nas Opções (macOS)."""
    from .charkit import find_mugen_exe
    if is_ikemen(root) or (app and is_app_bundle(app)):
        return find_ikemen_exe(root, app), "ikemen"
    return find_mugen_exe(root), "mugen"   # mugen.exe ou outro nome (ex.: MUGEN-ORIGINAL.exe)


def chosen_app(root: str | Path | None, ikemen_dir: str | Path | None) -> Path | None:
    """O bundle .app escolhido nas Opções, se for o da pasta em que o motor vai rodar."""
    if root and ikemen_dir and is_app_bundle(ikemen_dir) and Path(root) == Path(ikemen_dir).parent:
        return Path(ikemen_dir)
    return None


def _containing_engine(char: Character) -> Path | None:
    """Pasta do motor em cujo chars/ o personagem está."""
    for p in char.dir.parents:
        if (p / "chars").is_dir() and (p / "data").is_dir() and p / "chars" in char.dir.parents:
            return p
    return None


def engine_root(char: Character, engine: str = "auto", mugen_dir: str | Path | None = None,
                ikemen_dir: str | Path | None = None) -> tuple[Path | None, str]:
    """(pasta, motor) onde rodar: 'auto' usa o motor da pasta em que o personagem está; fora
    de uma, ZSS vai para o Ikemen GO e o resto para o MUGEN (ou o Ikemen, se só ele estiver
    configurado)."""
    if engine not in ENGINES:
        raise ValueError(tr("engine must be auto, mugen or ikemen"))
    ikemen = Path(ikemen_dir) if ikemen_dir else None
    mugen = Path(mugen_dir) if mugen_dir else (char.mugen_root or find_mugen_root(char.dir))
    # macOS: apontou o bundle .app em vez da pasta — a raiz é a pasta que o contém
    if ikemen and is_app_bundle(ikemen):
        ikemen = ikemen.parent
    if mugen and is_app_bundle(mugen):
        mugen = mugen.parent
    if mugen and is_ikemen(mugen) and not ikemen:
        ikemen = mugen                           # a "pasta do MUGEN" informada é um Ikemen
    ikemen = ikemen or char.ikemen_root()
    if engine == "auto":
        here = _containing_engine(char)
        if here:
            return here, "ikemen" if is_ikemen(here) else "mugen"
        if char.is_zss or not mugen or is_ikemen(mugen):
            engine = "ikemen" if ikemen else "mugen"
        else:
            engine = "mugen"
    root = ikemen if engine == "ikemen" else mugen
    return (Path(root) if root else None), engine


def engine_args(exe: Path, p1: str, p2: str | None = None, stage: str | None = None,
                p1_ai: int | None = None, p2_ai: int | None = None, rounds: int | None = None) -> list[str]:
    """Linha de comando da luta rápida; o MUGEN e o Ikemen GO aceitam a mesma: os dois
    personagens primeiro (relativos a chars/), depois -s, -pN.ai e -rounds."""
    args = [str(exe), p1, p2 or p1]
    if stage:
        args += ["-s", stage]
    if p1_ai is not None:
        args += ["-p1.ai", str(p1_ai)]
    if p2_ai is not None:
        args += ["-p2.ai", str(p2_ai)]
    if rounds:
        args += ["-rounds", str(rounds)]
    return args


def engine_log(root: Path, engine: str, since: float = 0) -> str | None:
    """Fim do log que o motor gravou depois de `since`: mugen.log, ou o do Ikemen GO
    (save/logs/Ikemen_<data>.log; versões antigas gravam Ikemen.log na pasta)."""
    if engine == "ikemen":
        logs = [*(root / "save" / "logs").glob("Ikemen*.log"), root / "Ikemen.log"]
    else:
        logs = [root / "mugen.log"]
    new = [p for p in logs if p.exists() and p.stat().st_size and p.stat().st_mtime > since]
    if not new:
        return None
    p = max(new, key=lambda q: q.stat().st_mtime)
    return p.read_text("utf-8" if engine == "ikemen" else "cp1252", errors="replace")[-4000:]


def run(char: Character, opponent: str | None = None, stage: str | None = None,
        mugen_root: str | Path | None = None, watch_seconds: float = 4.0,
        p1_ai: int | None = None, p2_ai: int | None = None, rounds: int | None = None,
        engine: str = "auto", ikemen_root: str | Path | None = None) -> dict:
    from .charkit import default_stage
    root, engine = engine_root(char, engine, mugen_root, ikemen_root)
    if not root:
        raise FileNotFoundError(tr("Ikemen GO folder not found; set ikemen_root") if engine == "ikemen"
                                else tr("MUGEN folder not found; set mugen_root"))
    if engine == "mugen" and char.is_zss:
        raise ValueError(tr("ZSS states only run in Ikemen GO"))
    exe, engine = engine_exe(root, chosen_app(root, ikemen_root))
    prepare_engine(exe)
    args = engine_args(exe, char_argument(char, root, engine), opponent, stage or default_stage(root),
                       p1_ai, p2_ai, rounds)
    started = time.time()
    proc = subprocess.Popen(args, cwd=root)
    time.sleep(watch_seconds)
    result = {"engine": engine, "pid": proc.pid, "args": args[1:], "running": proc.poll() is None,
              "exit_code": proc.poll()}
    problem = config_problem(root, engine)
    if problem:
        result["problem"] = problem
    log = engine_log(root, engine, started - 1)
    if log:
        result["mugen_log_tail" if engine == "mugen" else "log_tail"] = log[-3000:]
    return result
