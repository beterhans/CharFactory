"""Golpe em passos: quem pede diz só a sequência (soco, lançador, pulo, chute no ar) e a
animação de cada passo; daqui sai o MUGEN inteiro. Um statedef por passo, encadeados só se o
passo acertou, HitDefs com o atordoamento que dá tempo do próximo passo, lançamento, pulo,
juggle e aterrissagem. Os números que dependem do personagem (altura do lançamento, força do
pulo, quando o ataque aéreo começa) saem do simulador: algumas combinações são testadas e
fica a que faz mais passos acertarem.

É o caminho para a IA fazer golpes sem escrever CNS: ela escolhe poses e papéis, e as regras
do motor (hitstun, gravidade do oponente, encadear só no acerto) ficam no código.
"""
from __future__ import annotations

import copy
import re
from collections import Counter
from dataclasses import dataclass, field, replace

from . import movespec, ops

ROLES = {
    "strike": "ground hit; the opponent stays standing, stunned long enough for the next step",
    "launcher": "ground hit that throws the opponent up into the air",
    "jump": "the character jumps after the opponent, no hit (added on its own before the first "
            "air step that follows a ground step)",
    "air_strike": "hit in the air that keeps the opponent floating",
    "air_finisher": "last hit in the air: slams the opponent down",
    "finisher": "last ground hit: knocks the opponent down",
    "dash": "moves forward up to the opponent, no hit",
}
AIR_ROLES = {"jump", "air_strike", "air_finisher"}
HIT_ROLES = {"strike", "launcher", "air_strike", "air_finisher", "finisher"}
KINDS = ("normal", "special", "super")
MARK = "; build_move:"            # comentário dos estados gerados: refazer o golpe pode substituí-los

DAMAGE = {"strike": 25, "launcher": 35, "air_strike": 30, "air_finisher": 55, "finisher": 55}
KIND_MUL = {"normal": 0.7, "special": 1.0, "super": 1.8}
HOLD = 12            # ticks que um quadro infinito (-1) vale na conta da duração
MARGIN = 8           # folga do atordoamento além do que o próximo passo precisa
JUMP_ANIMS = (42, 41, 40)        # pulo para a frente, para cima, começo do pulo
# o que os acertos antes do último fazem num passo de vários acertos
LEAD_IN = {"launcher": "strike", "finisher": "strike", "air_finisher": "air_strike"}
LUNGE = 5            # velocidade máxima (px por tick) de um golpe no chão encostando no oponente


@dataclass
class Step:
    role: str
    anim: int
    state: int = 0
    damage: int | None = None
    hits: list[int] | None = None          # elementos (1 = primeiro) onde liga cada HitDef
    note: str = ""                          # o que o código fez sozinho (anim copiada, pulo posto)


@dataclass
class Tune:
    """Os números que o simulador escolhe."""
    launch_vy: float = -9.0
    launch_vx: float = -1.5
    jump_vy: float = -9.0
    lead: float = 20.0        # o ataque aéreo começa quando o char chega a `lead` px abaixo do oponente
    air_vy: float | None = -2.0   # VelSet y no começo de cada ataque aéreo (None: segue o pulo)
    pop: float = -4.0         # o ataque aéreo joga o oponente para cima de novo


CANDIDATES = {
    "launch_vy": [-9.0, -8.0, -10.0, -7.0, -11.0],
    "launch_vx": [-1.5, -0.8, -2.5],
    "jump_vy": [-9.0, -8.0, -10.0, -7.0, -11.0],
    "lead": [20.0, 0.0, 40.0, -10.0],
    "air_vy": [-2.0, -4.0, 0.0, None],
    "pop": [-4.0, -2.0, -6.0],
}
# qual parâmetro importa para qual papel (só esses são testados)
NEEDS = {"launch_vy": "launcher", "launch_vx": "launcher", "jump_vy": "jump", "lead": "jump",
         "air_vy": "air_strike", "pop": "air_strike"}


HEAVY = {"heavy", "hard", "up", "diagup", "back"}       # animtype de acerto forte


@dataclass
class House:
    """Como o próprio personagem faz os acertos, tirado dos golpes dele: sons, faíscas e a
    SuperPause. Chars no estilo JUS quase nunca usam o fightfx/fight.snd do motor (sparkno = -1 e
    a faísca feita por um Explod ou Helper no acerto, sons S do .snd próprio); um char sem golpes
    para copiar fica com os do motor."""
    hitsound: dict = field(default_factory=lambda: {"light": "5, 0", "heavy": "5, 2"})
    guardsound: str = "6, 0"
    sparkno: dict = field(default_factory=lambda: {"light": "0", "heavy": "2"})
    guard_sparkno: str = "40"
    spark: tuple | None = None          # (tipo, [(chave, valor)…]) do Explod/Helper de faísca
    superpause: dict | None = None      # parâmetros mais comuns das SuperPause do char


@dataclass
class Ctx:
    g: float = 0.44
    house: House = field(default_factory=House)


def _top(c: Counter, default):
    return c.most_common(1)[0][0] if c else default


def house(char) -> House:
    h = House()
    snd = {"light": Counter(), "heavy": Counter()}
    spk = {"light": Counter(), "heavy": Counter()}
    gsnd, gspk, pauses = Counter(), Counter(), {}
    for n, sds in sorted(char.all_statedefs(include_common=False).items()):
        sd = sds[0]
        if n < 0 or not hasattr(sd, "controllers") or MARK in sd.text():
            continue
        hits = [c for c in sd.controllers if c.type.lower() == "hitdef"]
        for c in hits:
            p = c.section.as_dict()
            w = "heavy" if (p.get("animtype") or "").strip().lower() in HEAVY else "light"
            for key, box in (("hitsound", snd[w]), ("sparkno", spk[w]), ("guardsound", gsnd),
                             ("guard.sparkno", gspk)):
                v = (p.get(key) or "").strip()
                if (v and not v.startswith("-1")) or (key == "sparkno" and v == "-1"):
                    box[v] += 1
        for c in sd.controllers:
            if c.type.lower() == "superpause":
                for k, v in c.section.as_dict().items():
                    if k in ("time", "movetime", "anim", "sound", "darken", "pos", "unhittable"):
                        pauses.setdefault(k, Counter())[v.strip()] += 1
        # a faísca que os golpes normais criam no acerto (Explod/Helper com MoveHit); o sparkno
        # deles vem junto como está (-1 ou um S inválido de propósito, para o motor não pôr a dele)
        if h.spark is None and 200 <= n < 700 and hits:
            for c in sd.controllers:
                trig = " ".join(v for vs in c.triggers().values() for v in vs).lower()
                if c.type.lower() in ("explod", "helper") and "movehit" in trig:
                    h.spark = (c.type, [(e.key, e.value) for e in c.section.entries()
                                        if e.key.lower() not in ("type", "persistent")
                                        and not e.key.lower().startswith("trigger")])
                    break
    for w in ("light", "heavy"):
        h.hitsound[w] = _top(snd[w], _top(snd["light" if w == "heavy" else "heavy"], h.hitsound[w]))
        got = _top(spk[w], _top(spk["light" if w == "heavy" else "heavy"], h.sparkno[w]))
        h.sparkno[w] = got if got != "-1" or h.spark else h.sparkno[w]     # -1 sem faísca própria: a do motor
    h.guardsound = _top(gsnd, h.guardsound)
    h.guard_sparkno = _top(gspk, h.guard_sparkno)
    if pauses:
        h.superpause = {k: _top(v, "") for k, v in pauses.items()}
    return h


class ComboError(ValueError):
    """Passos que não dão um golpe (papel desconhecido, animação que não existe)."""


# ====================================================================== animações

def _timing(act) -> tuple[list[int], int]:
    """Tick em que cada quadro começa e a duração da animação."""
    starts, t = [], 0
    for f in act.frames:
        starts.append(t)
        t += f.time if f.time > 0 else HOLD
    return starts, t


def _hit_elems(act) -> list[int]:
    """Um acerto por trecho seguido de quadros com Clsn1 (o HitDef liga no primeiro de cada)."""
    out, prev = [], False
    for k, f in enumerate(act.frames, 1):
        if f.clsn1 and not prev:
            out.append(k)
        prev = bool(f.clsn1)
    return out


def stand_height(char) -> float:
    from . import simulate
    try:
        return simulate.Sim(char, 0, max_ticks=1).stand_h
    except Exception:  # noqa: BLE001  (sem estado 0 ou sem SFF: altura padrão)
        return 60.0


def gravity(char) -> float:
    from . import simulate
    try:
        return float(simulate.Sim(char, 0, max_ticks=1).const("movement.yaccel")) or 0.44
    except Exception:  # noqa: BLE001
        return 0.44


def _free_anim(char, start: int) -> int:
    n = start
    while char.anims.get(n) is not None:
        n += 1
    return n


def with_attack_box(char, anim: int, kind: str, start: int) -> int:
    """Cópia da animação com Clsn1 no quadro que vai mais para a frente, para um passo de
    acerto cuja animação não tem caixa de ataque. Devolve o número da cópia."""
    act = char.anims.get(anim)
    best, reach, boxes = None, None, []
    for k, f in enumerate(act.frames):
        if f.group < 0 or "H" in (f.flip or "").upper():
            continue
        b = movespec.clsn1_auto(char, f.group, f.item)
        if b and (reach is None or max(x[2] for x in b) + f.x > reach):
            best, reach, boxes = k, max(x[2] for x in b) + f.x, b
    if best is None:
        raise ComboError(f"animation {anim} has no frame that reaches forward: pick another one")
    new = copy.deepcopy(act)
    new.number = _free_anim(char, start)
    for attr in ("_raw", "_snapshot", "_comments"):
        setattr(new, attr, None)
    f = new.frames[best]
    f.clsn1 = [(b[0] + f.x, b[1] + f.y, b[2] + f.x, b[3] + f.y)
               for b in movespec.grow_clsn1(boxes, stand_height(char), kind)]
    char.anims.set_action(new)
    char.mark("anims")
    return new.number


# ====================================================================== passos

def plan(char, raw: list[dict], kind: str) -> list[Step]:
    """Passos do pedido -> passos completos: papéis e animações conferidos e o pulo posto
    antes do primeiro passo aéreo que vem de um no chão."""
    if kind not in KINDS:
        raise ComboError(f"kind must be one of: {', '.join(KINDS)}")
    if not raw:
        raise ComboError("steps is empty: give at least one step")
    steps: list[Step] = []
    for k, r in enumerate(raw, 1):
        role = str(r.get("role", "")).strip().lower()
        if role not in ROLES:
            raise ComboError(f"step {k}: role {role!r} is not one of: {', '.join(ROLES)}")
        anim = r.get("anim")
        if anim is None and role == "jump":
            anim = next((a for a in JUMP_ANIMS if char.anims.get(a) is not None), None)
        if anim is None or char.anims.get(int(anim)) is None or not char.anims.get(int(anim)).frames:
            raise ComboError(f"step {k} ({role}): animation {anim} does not exist")
        hits = r.get("hits")
        steps.append(Step(role, int(anim), damage=r.get("damage"),
                          hits=[int(h) for h in hits] if hits else None))
    out: list[Step] = []
    for s in steps:
        if s.role in AIR_ROLES - {"jump"} and out and out[-1].role not in AIR_ROLES:
            a = next((a for a in JUMP_ANIMS if char.anims.get(a) is not None), s.anim)
            out.append(Step("jump", a, note="jump added before the air attack"))
        out.append(s)
    return out


def place(char, steps: list[Step], base: int, kind: str) -> None:
    """Um estado para cada passo (base, base + 1…) e Clsn1 onde a animação de um acerto não tem."""
    for k, s in enumerate(steps):
        s.state = base + k
        if s.role in HIT_ROLES and not s.hits and not _hit_elems(char.anims.get(s.anim)):
            old = s.anim
            s.anim = with_attack_box(char, old, kind, base + k)
            s.note = f"animation {old} has no attack box: copied to {s.anim} with one"


# ====================================================================== CNS

def _ctrl(state: int, kind: str, label: str, **kv) -> str:
    return re.sub(r"^\[State 0,", f"[State {state},", movespec._ctrl(kind, label, **kv))


def _num(v: float) -> str:
    return f"{v:g}"


def _startup(char, s: Step) -> int:
    """Ticks até o primeiro acerto do passo (ou a duração, num passo sem acerto)."""
    act = char.anims.get(s.anim)
    starts, dur = _timing(act)
    elems = s.hits or _hit_elems(act)
    return starts[elems[0] - 1] if s.role in HIT_ROLES and elems else dur


def _recovery_start(act, elems: list[int]) -> int:
    """Tick em que o último trecho de Clsn1 acaba: dali o próximo passo já pode entrar."""
    starts, dur = _timing(act)
    k = elems[-1] - 1
    while k < len(act.frames) and act.frames[k].clsn1:
        k += 1
    return starts[k] if k < len(act.frames) else dur


def _reach(char, s: Step) -> int:
    act = char.anims.get(s.anim)
    elems = s.hits or _hit_elems(act)
    f = act.frames[elems[0] - 1] if elems else act.frames[0]
    return max((b[2] for b in f.clsn1), default=30)


def _hitdef(char, s: Step, elem: int, kind: str, t: Tune, ctx: Ctx, hittime: int, role: str) -> dict:
    """HitDef de um acerto do passo; `role` é o que este acerto faz (num lançador de vários
    acertos, só o último lança: os anteriores seguram o oponente como um soco)."""
    act = char.anims.get(s.anim)
    f = act.frames[elem - 1]
    y = int(sum((b[1] + b[3]) / 2 for b in f.clsn1) / len(f.clsn1)) if f.clsn1 else -40
    air = s.role in AIR_ROLES
    tier = {"normal": "N", "special": "S", "super": "H"}[kind]
    n_hits = max(1, len(s.hits or _hit_elems(act)))
    dmg = int(s.damage if s.damage is not None else DAMAGE[s.role] * KIND_MUL[kind] / n_hits)
    h = ctx.house
    w = "light" if role in ("strike", "air_strike") else "heavy"
    kv = dict(trigger1=f"animelem = {elem}", attr=f"{'A' if air else 'S'}, {tier}A",
              damage=f"{dmg}, {max(0, dmg // 8)}", guardflag="HA" if air else "MA", hitflag="MAF",
              animtype="Medium", priority="3, Hit", pausetime="8, 8", sparkno=h.sparkno[w],
              guard__sparkno=h.guard_sparkno, sparkxy=f"-10, {y}", hitsound=h.hitsound[w],
              guardsound=h.guardsound, ground__type="High", ground__slidetime=min(hittime, 12),
              ground__hittime=hittime, ground__velocity="-1.5", air__velocity="-1.5, -3",
              yaccel=_num(ctx.g))
    if role == "launcher":
        v = f"{_num(t.launch_vx)}, {_num(t.launch_vy)}"
        kv.update(animtype="Up", pausetime="10, 10", ground__velocity=v, air__velocity=v, fall=1,
                  fall__recover=0)
    elif role == "air_strike":
        kv.update(air__velocity=f"-1.2, {_num(t.pop)}", ground__velocity=f"-2, {_num(t.pop)}", fall=1,
                  fall__recover=0, air__fall=1)
    elif role in ("air_finisher", "finisher"):
        kv.update(animtype="Heavy", pausetime="12, 12", fall=1, fall__recover=0,
                  envshake__time=12, envshake__ampl=-4, envshake__freq=60)
        if role == "air_finisher":
            kv.update(air__velocity="-2.5, 6", ground__velocity="-4, -3")
        else:
            kv.update(ground__velocity="-6, -5", air__velocity="-5, -4")
    return kv


def state_text(char, steps: list[Step], k: int, kind: str, name: str, t: Tune, ctx: Ctx) -> str:
    s = steps[k]
    nxt = steps[k + 1] if k + 1 < len(steps) else None
    act = char.anims.get(s.anim)
    starts, dur = _timing(act)
    air = s.role in AIR_ROLES
    first = k == 0
    n = s.state
    head = [f"[Statedef {n}]",
            f"{MARK} {name} (move {steps[0].state}), step {k + 1} of {len(steps)} ({s.role})",
            f"type = {'A' if air else 'S'}", f"movetype = {'I' if s.role in ('jump', 'dash') else 'A'}",
            # N no chão: o atrito da física S comeria a aproximação (o VelSet "stop" a encerra)
            f"physics = {'A' if air else 'N'}", f"juggle = {2 if air else 1}",
            "ctrl = 0", f"anim = {s.anim}", "sprpriority = 2"]
    if not air:
        head.append("velset = 0, 0")
        if first:
            head.append("facep2 = 1")
    if first and kind == "super":
        head.append("poweradd = -1000")
    out = "\n".join(head) + "\n\n"
    if first and kind == "super":
        # a SuperPause como o char faz as dele (no estilo JUS: sem a anim e o som do motor)
        sp = {"time": 30, "movetime": 0, "anim": 100, "sound": "20, 0", "darken": 1, "unhittable": 1}
        sp.update(ctx.house.superpause or {})
        out += _ctrl(n, "SuperPause", "super pause", trigger1="!time", **sp, poweradd=0)
    # distância (entre as frentes dos corpos) em que a Clsn1 ainda entra no oponente: o dash usa o
    # alcance do golpe que vem depois dele, o passo encadeado o próprio
    aim = nxt if s.role == "dash" and nxt and nxt.role in HIT_ROLES else s
    gap = max(0, min(40, _reach(char, aim) - 28))
    dist = f"(p2bodydist x - {gap})" if gap else "p2bodydist x"
    if s.role == "dash":
        out += _ctrl(n, "VelSet", "run up to the opponent", trigger1="!time",
                     x=f"ifelse(p2bodydist x > {gap}, {dist} / {max(1, dur)}.0, 0)")
    elif not air and s.role in HIT_ROLES:
        # golpe no chão: encosta no oponente até o alcance da Clsn1 (o acerto anterior o empurrou;
        # no 1º passo, faz as vezes do passo à frente que os golpes desses chars dão), no máximo
        # LUNGE px por tick
        ticks = max(2, min(_startup(char, s), 8))
        far = gap + LUNGE * ticks
        out += _ctrl(n, "VelSet", "close in", trigger1="!time",
                     x=f"ifelse(p2bodydist x > {far}, {LUNGE}, ifelse(p2bodydist x > {gap}, {dist} / {ticks}.0, 0))")
        out += _ctrl(n, "VelSet", "stop", trigger1=f"time = {ticks}", x=0)
    if s.role == "jump":
        rise = max(4.0, -t.jump_vy / ctx.g)
        drift = -t.launch_vx if any(x.role == "launcher" for x in steps[:k]) else 0.0
        out += _ctrl(n, "VelSet", "jump after the opponent", trigger1="!time",
                     x=f"ifelse(p2dist x > 0, (p2dist x - 10) / {rise:.1f} + {_num(drift)}, 0)",
                     y=_num(t.jump_vy))
    elif air and t.air_vy is not None:
        out += _ctrl(n, "VelSet", "stay up for the hit", trigger1="!time", y=_num(t.air_vy))
    if s.role in HIT_ROLES:
        elems = s.hits or _hit_elems(act)
        rec = _recovery_start(act, elems)
        if nxt is None or nxt.role in AIR_ROLES:
            stun = 15
        else:
            follow = _startup(char, nxt)
            if nxt.role == "dash" and k + 2 < len(steps):
                follow += _startup(char, steps[k + 2])
            stun = max(12, rec - starts[elems[0] - 1] + follow + MARGIN)
        spark = ctx.house.spark
        for j, e in enumerate(elems):
            nxt_e = elems[j + 1] if j + 1 < len(elems) else None
            if nxt_e is None:
                role, hold = s.role, stun
            else:                     # acerto do meio: segura até o próximo trecho de Clsn1
                role, hold = LEAD_IN.get(s.role, s.role), starts[nxt_e - 1] - starts[e - 1] + MARGIN
            out += _ctrl(n, "HitDef", f"hit {e}", **_hitdef(char, s, e, kind, t, ctx, hold, role))
            if spark:
                # a faísca do char, uma por acerto: vale do quadro deste acerto até o do próximo
                trig = f"(movehit = 1) && (animelem = {e}, >= 0)" + (
                    f" && (animelem = {nxt_e}, < 0)" if nxt_e else "")
                out += _ctrl(n, spark[0], "hit spark", trigger1=trig, persistent=0,
                             **{k.replace(".", "__"): v for k, v in spark[1]})
    else:
        rec = dur
    if air:
        out += _ctrl(n, "ChangeState", "land", trigger1="(pos y >= 0) && (vel y > 0)", value=52)
    if nxt is not None:
        if s.role == "jump":
            out += _ctrl(n, "ChangeState", "attack when level with the opponent",
                         trigger1=f"(time >= 2) && ((p2dist y >= {_num(-t.lead)}) || (vel y >= 0))",
                         value=nxt.state)
        elif s.role == "dash":
            out += _ctrl(n, "ChangeState", "next step", trigger1=f"time >= {dur}", value=nxt.state)
        else:
            out += _ctrl(n, "ChangeState", "next step if it hit",
                         trigger1=f"(movecontact) && (time >= {rec})", value=nxt.state)
    if air:
        if any(f.time < 0 for f in act.frames):
            return out                      # quadro infinito: cai até a aterrissagem
        return out + _ctrl(n, "ChangeState", "fall", trigger1=f"time >= {dur}", value=50, ctrl=0)
    return out + _ctrl(n, "ChangeState", "end", trigger1=f"time >= {dur}", value=0, ctrl=1)


def leftovers(char, base: int, count: int) -> list[int]:
    """Estados que uma versão anterior do golpe (com mais passos) deixou depois dos atuais."""
    out, n, defs = [], base + count, char.all_statedefs(include_common=False)
    while n in defs and f"(move {base})" in defs[n][0].text() and MARK in defs[n][0].text():
        out.append(n)
        n += 1
    return out


def write(char, steps: list[Step], kind: str, name: str, t: Tune, ctx: Ctx) -> None:
    for k, s in enumerate(steps):
        ops.set_statedef_text(char, s.state, state_text(char, steps, k, kind, name, t, ctx))


# ====================================================================== simulação e ajuste

@dataclass
class Report:
    hit: dict = field(default_factory=dict)     # estado -> tick do primeiro acerto (ou None)
    hits: int = 0
    ticks: int = 0
    falls: bool = False


def run(char, steps: list[Step], dist: float) -> Report:
    from . import simulate
    first = steps[0]
    sim = simulate.simulate(char, first.state, p2_dist=dist, max_ticks=700,
                            from_ground=first.role not in AIR_ROLES)
    r = Report(hit={s.state: None for s in steps if s.role in HIT_ROLES}, ticks=sim.tick)
    for e in sim.events:
        if e["kind"] == "acerto" and e.get("who") == "P1":
            r.hits += 1
            r.falls = r.falls or bool(e.get("fall"))
            if r.hit.get(e.get("state"), 0) is None:
                r.hit[e["state"]] = e["t"]
    return r


def _score(char, steps, dists) -> tuple[int, int]:
    reps = [run(char, steps, d) for d in dists]
    # passos que acertam em sequência contam mais que um acerto solto depois de um erro
    chained = 0
    for r in reps:
        for s in steps:
            if s.state in r.hit:
                if r.hit[s.state] is None:
                    break
                chained += 1
    return chained, sum(r.hits for r in reps)


def tune(char, steps: list[Step], kind: str, name: str, dists=(40.0, 60.0), passes: int = 2) -> Tune:
    """Descida por coordenadas: cada número testado com os outros fixos, fica o que faz mais
    passos acertarem em sequência (empate: o valor que já estava, o mais comum)."""
    ctx = Ctx(gravity(char), house(char))
    roles = {s.role for s in steps}
    keys = [k for k, role in NEEDS.items() if role in roles]
    best = Tune()
    write(char, steps, kind, name, best, ctx)
    score = _score(char, steps, dists)
    full = (len(dists) * sum(1 for s in steps if s.role in HIT_ROLES),)
    for _ in range(passes):
        changed = False
        for key in keys:
            for v in CANDIDATES[key]:
                if v == getattr(best, key):
                    continue
                cand = replace(best, **{key: v})
                write(char, steps, kind, name, cand, ctx)
                sc = _score(char, steps, dists)
                if sc > score:
                    best, score, changed = cand, sc, True
            if score[:1] == full:
                break
        if not changed or score[:1] == full:
            break
    write(char, steps, kind, name, best, ctx)
    return best
