"""Testador de comandos: dada uma sequência de entradas, quais [Command] do .cmd ela aciona.

Entrada em notação de numpad, um passo por espaço (o lado é sempre "para a frente"):
    2 3 6 a          ↓ ↘ → + A   (meia-lua para frente + A)
    6 2 3 x+y        Z para frente + X e Y juntos
    4*40 6 a         segura para trás 40 ticks, frente, A (carga)
    a*30 ~a          segura A 30 ticks e solta
Cada passo dura 1 tick (ou `*n`); `5` é neutro. Também aceita os nomes do MUGEN
(D, DF, F, a…) no lugar dos números.

A comparação segue as regras da documentação da Elecbyte (cmd.html): `/` segura, `~` solta
(com `~30` exigindo 30 ticks segurando antes), `$` aceita a direção contida em diagonais,
`>` não permite outra entrada entre os dois passos e `+` aperta junto. O resultado é uma
aproximação do buffer do MUGEN, útil para achar comando que conflita ou que não sai.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from ..i18n import tr

NUMPAD = {"1": "DB", "2": "D", "3": "DF", "4": "B", "5": "", "6": "F", "7": "UB", "8": "U", "9": "UF"}
DIRS = {"B", "DB", "D", "DF", "F", "UF", "U", "UB"}
BUTTONS = {"a", "b", "c", "x", "y", "z", "s"}


def _dir_parts(d: str) -> set[str]:
    return {c for c in d} if d else set()     # "DF" -> {"D", "F"}


@dataclass
class Tick:
    direction: str            # "", "F", "DF"...
    buttons: frozenset


def parse_input(text: str) -> list[Tick]:
    """Lista de ticks a partir da notação (ver o módulo)."""
    ticks: list[Tick] = []
    held_buttons: set[str] = set()
    for raw in text.replace(",", " ").split():
        m = re.match(r"^(.*?)(?:\*(\d+))?$", raw)
        body, n = m[1], int(m[2] or 1)
        direction = ""
        buttons: set[str] = set()
        release: set[str] = set()
        for part in body.split("+"):
            p = part.strip()
            if not p:
                continue
            if p.startswith("~"):
                release.add(p[1:].lower())
                continue
            if p in NUMPAD:
                direction = NUMPAD[p]
            elif p in DIRS:                       # como no .cmd: B maiúsculo é trás, b é o botão
                direction = p
            elif p.lower() in BUTTONS:
                buttons.add(p.lower())
            elif p.upper() in DIRS:
                direction = p.upper()
            else:
                raise ValueError(tr("unknown input '{0}'").format(p))
        if release:
            held_buttons -= release
            # a direção/botões continuam como estavam; o tick só registra a soltura
            last_dir = ticks[-1].direction if ticks else ""
            ticks.extend(Tick(direction or last_dir, frozenset(held_buttons)) for _ in range(n))
            continue
        prev = ticks[-1] if ticks else None
        if prev and ((direction and direction == prev.direction) or buttons & prev.buttons):
            # o mesmo passo de novo é outro toque (6 6 = dash): solta um tick entre os dois
            ticks.append(Tick("" if direction == prev.direction else prev.direction, prev.buttons - buttons))
        held = set(buttons) if n > 1 else set()
        ticks.extend(Tick(direction, frozenset(buttons | (held if k else set()))) for k in range(n))
        held_buttons = held
    return ticks


@dataclass
class Step:
    elems: list[tuple[str, str, int]]   # (modo, símbolo, ticks de carga) — modo: press/hold/release/contains
    strict: bool                         # '>' antes do passo


def parse_command(seq: str) -> list[Step]:
    steps = []
    for raw in seq.split(","):
        s = raw.strip()
        strict = s.startswith(">")
        s = s.lstrip(">").strip()
        elems = []
        for part in s.split("+"):
            p = part.strip()
            mode, charge = "press", 0
            m = re.match(r"^~(\d*)(.*)$", p)
            if m:
                mode, charge, p = "release", int(m[1] or 0), m[2].strip()
            if p.startswith("/"):
                mode, p = ("hold" if mode == "press" else mode), p[1:].strip()
            contains = p.startswith("$")
            p = p.lstrip("$").strip()
            if contains and mode == "press":
                mode = "contains"
            elif contains and mode == "hold":
                mode = "hold_contains"
            elif contains and mode == "release":
                mode = "release_contains"
            elems.append((mode, p, charge))
        steps.append(Step(elems, strict))
    return steps


def _active(t: Tick, sym: str, contains: bool) -> bool:
    if sym in BUTTONS:
        return sym in t.buttons
    if contains:
        return _dir_parts(sym) <= _dir_parts(t.direction)
    return t.direction == sym


def _elem_at(ticks: list[Tick], i: int, mode: str, sym: str, charge: int) -> bool:
    cur = ticks[i]
    prev = ticks[i - 1] if i > 0 else Tick("", frozenset())
    if mode in ("hold", "hold_contains"):
        return _active(cur, sym, mode == "hold_contains")
    if mode in ("release", "release_contains"):
        c = mode == "release_contains"
        if not (_active(prev, sym, c) and not _active(cur, sym, c)):
            return False
        if charge:
            k, held = i - 1, 0
            while k >= 0 and _active(ticks[k], sym, c):
                held += 1
                k -= 1
            return held >= charge
        return True
    contains = mode == "contains"
    if sym in BUTTONS:                                  # botão: aperto neste tick
        return sym in cur.buttons and sym not in prev.buttons
    return _active(cur, sym, contains) and not _active(prev, sym, contains)


def _step_at(ticks: list[Tick], i: int, step: Step) -> bool:
    return all(_elem_at(ticks, i, m, s, c) for m, s, c in step.elems)


def _changed(ticks: list[Tick], i: int) -> bool:
    if i == 0:
        return bool(ticks[0].direction or ticks[0].buttons)
    return ticks[i].direction != ticks[i - 1].direction or ticks[i].buttons != ticks[i - 1].buttons


def matches(ticks: list[Tick], seq: str, time: int = 15, buffer_time: int = 1) -> int | None:
    """Tick em que o comando completa (o último que cabe no buffer), ou None."""
    steps = parse_command(seq)
    n = len(ticks)
    best = None
    for end in range(n):
        if not _step_at(ticks, end, steps[-1]):
            continue
        # busca para trás os passos anteriores dentro de `time`
        pos = end
        ok = True
        for k in range(len(steps) - 2, -1, -1):
            found = None
            # soltar e apertar a próxima direção acontecem no mesmo tick (D -> DF solta o D)
            same = any(m.startswith("release") for m, _, _ in steps[k].elems)
            for j in range(pos - (0 if same else 1), max(-1, end - time - 1), -1):
                if _step_at(ticks, j, steps[k]):
                    found = j
                    break
                if steps[k + 1].strict and _changed(ticks, j):
                    break
            if found is None:
                ok = False
                break
            pos = found
        if ok:
            best = end
    return best


def test(char, text: str) -> dict:
    """Comandos do personagem que a entrada aciona no último tick (e os que completam antes)."""
    return test_ticks(char, parse_input(text))


def test_ticks(char, ticks: list[Tick]) -> dict:
    if not ticks:
        return {"ticks": 0, "active": [], "earlier": []}
    active, earlier = [], []
    for c in char.commands.commands():
        try:
            t = int((c.section.get("time") or "15").split(";")[0])
        except ValueError:
            t = 15
        try:
            bt = int((c.section.get("buffer.time") or "1").split(";")[0])
        except ValueError:
            bt = 1
        try:
            at = matches(ticks, c.sequence, t, bt)
        except (ValueError, IndexError):
            continue
        any_at = None
        try:
            any_at = matches(ticks, c.sequence, t, len(ticks) + 1)
        except (ValueError, IndexError):
            pass
        row = {"name": c.name, "command": c.sequence, "time": t, "tick": at if at is not None else any_at}
        if at is not None and at >= len(ticks) - bt:
            active.append(row)
        elif any_at is not None:
            earlier.append(row)
    # o estado que cada comando ativo leva, pelo [Statedef -1]
    entries: dict[str, list[int]] = {}
    sd = char.commands.states.statedefs.get(-1)
    for ctl in (sd.controllers if sd else []):
        if ctl.type.lower() != "changestate":
            continue
        v = re.match(r"^\s*(\d+)", ctl.section.get("value") or "")
        for ex in ctl.triggers().values():
            for e in ex:
                for name in re.findall(r'command\s*=\s*"([^"]+)"', e, re.I):
                    if v:
                        entries.setdefault(name.lower(), []).append(int(v[1]))
    for row in active + earlier:
        row["states"] = sorted(set(entries.get(row["name"].lower(), [])))
    return {"ticks": len(ticks), "active": active, "earlier": earlier}


# ================================================================ [Statedef -1]

POSES = {"stand": 0, "crouch": 11, "air": 50}       # estado de onde o jogador aperta
_CMD_REF = re.compile(r'command\s*=\s*"([^"]+)"', re.I)


def sequence_ticks(seq: str) -> list[Tick] | None:
    """A entrada mais curta que completa o comando (None se não der para montar uma)."""
    ticks: list[Tick] = []
    cur = Tick("", frozenset())

    def push(t: Tick):
        nonlocal cur
        ticks.append(t)
        cur = t

    try:
        steps = parse_command(seq)
    except (ValueError, IndexError):
        return None
    for step in steps:
        direction, buttons = None, set()
        for mode, sym, charge in step.elems:
            if mode.startswith("release"):
                held = Tick(sym if sym not in BUTTONS else cur.direction,
                            cur.buttons | ({sym} if sym in BUTTONS else set()))
                for _ in range(max(charge, 1) - (1 if cur == held else 0)):
                    push(held)
                if sym not in BUTTONS:
                    direction = direction or ""
            elif sym in BUTTONS:
                if mode != "hold" and sym in cur.buttons:      # apertar de novo: solta antes
                    push(Tick(cur.direction, cur.buttons - {sym}))
                buttons.add(sym)
            else:
                if mode in ("press", "contains") and _active(cur, sym, mode == "contains"):
                    push(Tick("", frozenset()))                # F, F: volta ao neutro no meio
                direction = sym
        keep = {b for b in cur.buttons if any(m == "hold" and s == b for m, s, _ in step.elems)}
        push(Tick(cur.direction if direction is None else direction, frozenset(buttons | keep)))
    try:
        ok = matches(ticks, seq, len(ticks) + 1) == len(ticks) - 1
    except (ValueError, IndexError):
        ok = False
    return ticks if ok else None


def entry_commands(ctl) -> list[str]:
    """Nomes de comando que uma entrada do [Statedef -1] testa."""
    return [n for ex in ctl.triggers().values() for e in ex for n in _CMD_REF.findall(e)]


def pose_ticks(ticks: list[Tick], pose: str) -> list[Tick]:
    """A entrada feita agachado: segurando para baixo antes e durante (F vira DF)."""
    if pose != "crouch":
        return ticks
    down = {"": "D", "F": "DF", "B": "DB"}
    return [Tick("D", frozenset())] + [Tick(down.get(t.direction, t.direction), t.buttons) for t in ticks]


def route(char, commands, pose: str = "stand", distance: float = 50.0) -> list[dict]:
    """Entradas ChangeState do [Statedef -1] que disparam com estes comandos ativos, com o
    jogador parado em `pose` e com controle, na ordem do arquivo: a primeira é a que o motor usa.
    VarSet/VarAdd do [Statedef -1] rodam no caminho (muitos chars guardam ali a condição de combo)."""
    from .simulate import Sim
    sim = Sim(char, POSES[pose], p2_dist=distance, commands=tuple(commands), max_ticks=1)
    sim.p1.ctrl = 1
    sd = sim.statedef(-1)
    out = []
    for c in (sd[1] if sd else []):
        kind = c.get("type")
        if kind in ("varset", "varadd", "varrangeset"):
            if sim._triggered(sim.p1, c):
                sim.exec(sim.p1, c)
            continue
        if kind != "changestate" or not sim._triggered(sim.p1, c):
            continue
        v = re.match(r"^\s*(-?\d+)", c["params"].get("value", ""))
        label = re.sub(r"^\s*-1\s*,\s*", "", c["label"])          # "-1, Soco" -> "Soco"
        out.append({"index": c["index"], "label": label, "state": int(v[1]) if v else None})
    return out


def check_entry(char, index: int) -> dict:
    """Para onde vai o comando de uma entrada do [Statedef -1]: se ela dispara e, se não, qual
    entrada anterior toma a entrada antes (`taken_by`) e se as duas usam a mesma entrada."""
    states = char.states_file_for(-1)
    ctl = states.statedefs[-1].controllers[index]
    names = entry_commands(ctl)
    out: dict = {"label": ctl.label, "commands": names}
    found = [c for n in names for c in char.commands.find(n)]
    ticks = sequence_ticks(found[0].sequence) if found else None
    if ticks is None:
        out["unknown"] = ("command not defined in the .cmd: " + ", ".join(names)) if names and not found \
            else "no command to test"
        return out
    out["input"] = found[0].sequence
    for pose, distance in [(p, d) for d in (50.0, 1.0) for p in POSES]:
        active = [r["name"] for r in test_ticks(char, pose_ticks(ticks, pose))["active"]]
        fired = route(char, active, pose, distance)
        if any(f["index"] == index for f in fired):
            out["pose"], out["distance"] = pose, distance
            if fired[0]["index"] != index:
                first = fired[0]
                out["taken_by"] = first
                other = states.statedefs[-1].controllers[first["index"]]
                theirs = [c for n in entry_commands(other) for c in char.commands.find(n)]
                t2 = sequence_ticks(theirs[0].sequence) if theirs else None
                act2 = ({r["name"].lower() for r in test_ticks(char, pose_ticks(t2, pose))["active"]}
                        if t2 else set())
                out["same_input"] = any(n.lower() in act2 for n in names)
            return out
    out["never_fires"] = True
    return out


def place_entry(char, index: int) -> dict:
    """Confere a entrada `index` do [Statedef -1] e, se um golpe anterior pega a entrada dela
    (o soco fraco antes da meia-lua + soco), sobe ela para logo antes dele."""
    r = check_entry(char, index)
    states = char.states_file_for(-1)
    if "taken_by" in r and not r["same_input"] and hasattr(states, "reorder_controllers"):
        n = len(states.statedefs[-1].controllers)
        order = [i for i in range(n) if i != index]
        order.insert(order.index(r["taken_by"]["index"]), index)
        states.reorder_controllers(-1, order)
        r["moved_before"] = r.pop("taken_by")
        r.pop("same_input")
    return r


def input_owner(char, seq: str, pose: str = "stand") -> dict | None:
    """A entrada do [Statedef -1] que já usa exatamente esta sequência (a meia-lua + soco de
    outro especial), ou None. Um normal que só usa o botão não conta: o golpe novo vai antes dele."""
    ticks = sequence_ticks(seq)
    if ticks is None:
        return None
    ticks = pose_ticks(ticks, pose)
    active = [r["name"] for r in test_ticks(char, ticks)["active"]]
    entries = char.states_file_for(-1).statedefs.get(-1)
    for f in route(char, active, pose):
        theirs = [c for n in entry_commands(entries.controllers[f["index"]]) for c in char.commands.find(n)]
        t2 = sequence_ticks(theirs[0].sequence) if theirs else None
        if t2 is not None:
            t2 = pose_ticks(t2, pose)
            if matches(t2, seq, len(t2) + 1) == len(t2) - 1:
                return f
    return None


MOTIONS = ("~D, DF, F", "~D, DB, B", "~F, D, DF", "~B, D, DB", "~F, DF, D, DB, B", "~B, DB, D, DF, F",
           "~D, D", "F, F")


def free_inputs(char, buttons=("x", "y", "a", "b", "c", "z"), pose: str = "stand", limit: int = 10) -> list[str]:
    """Movimentos comuns + botão que nenhum golpe do personagem usa ainda."""
    out = []
    for motion in MOTIONS:
        for b in buttons:
            seq = f"{motion}, {b}"
            if input_owner(char, seq, pose) is None:
                out.append(seq)
                if len(out) >= limit:
                    return out
    return out
