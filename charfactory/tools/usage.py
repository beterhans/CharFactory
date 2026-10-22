"""Recursos não usados: sprites, animações e sons que nada referencia.

Uma referência conta quando o número é literal:
- sprite: usado por algum frame de alguma animação; os grupos 5000–5999 (tomar golpe, que os
  arremessos do oponente usam pelos estados dele) e 9000–9999 (retratos do screenpack) não
  entram na lista;
- animação: `anim` de statedef/Explod/Helper/Projectile, `value` de ChangeAnim/ChangeAnim2,
  `proj*anim`, `sparkno`/`guard.sparkno` com S, animações exigidas pelos estados comuns e as
  faixas reservadas do MUGEN (0–199 movimentos básicos, 5000–5999 tomar golpe), que o motor
  escolhe sozinho;
- som: `value` de PlaySnd sem F (com ou sem S), `hitsound`/`guardsound` com S, também nos
  estados comuns, e o 11,0, que o motor toca no KO.
Referências calculadas (expressões como `value = 200 + var(1)`) não dão o número exato. Os
números literais delas contam como usados e `N + random%K` cobre N..N+K-1; quando sobra uma
parte desconhecida (var, anim…), os recursos logo depois do número vão para `maybe_*`:
"talvez usados", para conferir antes de apagar.
"""
from __future__ import annotations

import re

from ..project import Character, ProjectError
from ..validate import required_anims
from ..i18n import tr

PORTRAIT_GROUP = 9000
RESERVED_ANIMS = (range(0, 200), range(5000, 6000))
RESERVED_SPRITE_GROUPS = (range(5000, 6000), range(9000, 10000))
RESERVED_SOUNDS = {(11, 0)}      # grito de KO: o motor toca sozinho
MAYBE_SPAN = 100                 # base + parte desconhecida: confere até base+99

_ANIM_KEYS = {"anim", "projanim", "projhitanim", "projremanim", "projcancelanim"}
_SPARK_KEYS = {"sparkno", "guard.sparkno"}
_INT = re.compile(r"^\s*[sS]?\s*(-?\d+)\s*$")
_SND = re.compile(r"^\s*(?:[sS]\s*)?(\d+)\s*,\s*(\d+)\s*$")
_OWN_SND = re.compile(r"^\s*S\s*(\d+)\s*,\s*(\d+)\s*$", re.I)
_OWN_SPARK = re.compile(r"^\s*S\s*(\d+)\s*$", re.I)
_LIT = re.compile(r"(?<![\w.])(\d+)(?![\w.])")
_CALL = re.compile(r"[a-z_]\w*\s*\(\s*\d+\s*\)", re.I)
_RANDOM = re.compile(r"random\s*%\s*(\d+)", re.I)
_UNKNOWN = re.compile(r"[a-z_]", re.I)


def _split_top(val: str) -> list[str]:
    """Separa por vírgulas fora de parênteses (grupo, número de um som)."""
    out, depth, cur = [], 0, ""
    for ch in val:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    return out + [cur]


def _expr_numbers(expr: str) -> tuple[set[int], set[int]]:
    """Números que uma expressão pode dar: (certos, bases com parte desconhecida).

    Os literais contam; `N + random%K` acrescenta N..N+K-1. Se, tirando o random, ainda há
    algo que não é número (var, anim, GetHitVar…), os literais também são bases de "talvez"."""
    mods = {int(m) for m in _RANDOM.findall(expr)}
    rest = _CALL.sub(" x ", _RANDOM.sub("", expr))     # var(10): o 10 não é animação nem som
    lits = {int(m) for m in _LIT.findall(rest)}
    sure = set(lits)
    k = max(mods, default=0)
    if k:
        for n in lits:
            sure.update(range(n, n + k))
        if not lits:
            sure.update(range(k))             # só random%K: 0..K-1
    unknown = bool(_UNKNOWN.search(rest))
    return sure, (lits if unknown else set())


def references(char: Character) -> dict:
    """Animações e sons referenciados pelos estados (do personagem e comuns)."""
    anims: set[int] = set()
    sounds: set[tuple[int, int]] = set()
    maybe_anims: set[int] = set()            # bases de expressões com parte desconhecida
    sound_groups: set[int] = set()           # grupo literal, número calculado: talvez qualquer um
    random_sounds: set[tuple[int, int]] = set()
    dynamic: list[str] = []

    def dyn_anim(expr: str, where: str) -> None:
        dynamic.append(where)
        sure, maybe = _expr_numbers(expr)
        anims.update(sure)
        maybe_anims.update(maybe)

    def dyn_sound(expr: str, where: str) -> None:
        dynamic.append(where)
        parts = _split_top(re.sub(r"^\s*[sS](?=\s*\d)", "", expr))
        if len(parts) < 2 or not _INT.match(parts[0]):
            return                            # grupo calculado: não há o que deduzir
        g = int(_INT.match(parts[0])[1])
        sure, maybe = _expr_numbers(parts[1])
        if _RANDOM.search(parts[1]) and not maybe:
            random_sounds.update((g, n) for n in sure)
        else:
            sound_groups.add(g)

    files = [*char.states, char.commands.states]
    if char.common_states:
        files.append(char.common_states)
    for st in files:
        for n, sd in st.statedefs.items():
            v = sd.section.get("anim")
            if v:
                v = v.split(";")[0]
                m = _INT.match(v)
                (anims.add(int(m[1])) if m else dyn_anim(v, f"[Statedef {n}] anim = {v.strip()}"))
            for c in sd.controllers:
                t = c.type.lower()
                for e in c.section.entries():
                    key, val = e.key.lower(), (e.value or "").split(";")[0]
                    where = f"[State {n}, {c.label}] {e.key} = {val.strip()}"
                    if key in _ANIM_KEYS or (key == "value" and t in ("changeanim", "changeanim2")):
                        if val.strip().upper().startswith("F"):
                            continue  # animação do fightfx, não do personagem
                        m = _INT.match(val)
                        (anims.add(int(m[1])) if m else dyn_anim(val, where))
                    elif key in _SPARK_KEYS:
                        m = _OWN_SPARK.match(val)     # sem S a faísca é do fightfx
                        if m:
                            anims.add(int(m[1]))
                    elif key == "value" and t == "playsnd":
                        if val.strip().upper().startswith("F"):
                            continue
                        m = _SND.match(val)
                        (sounds.add((int(m[1]), int(m[2]))) if m else dyn_sound(val, where))
                    elif key in ("hitsound", "guardsound"):
                        m = _OWN_SND.match(val)
                        if m:
                            sounds.add((int(m[1]), int(m[2])))
    return {"anims": anims, "sounds": sounds | random_sounds, "maybe_anims": maybe_anims,
            "sound_groups": sound_groups, "dynamic": dynamic}


def unused_resources(char: Character) -> dict:
    refs = references(char)
    try:
        actions = char.anims.actions
    except ProjectError:
        actions = {}
    used_sprites = {(f.group, f.item) for a in actions.values() for f in a.frames}
    sprites = [[s.group, s.item] for s in char.sprites.sprites
               if not any(s.group in r for r in RESERVED_SPRITE_GROUPS) and (s.group, s.item) not in used_sprites]
    keep = refs["anims"] | required_anims(char)
    free = [n for n in sorted(actions) if n not in keep and not any(n in r for r in RESERVED_ANIMS)]
    near = lambda n: any(b <= n < b + MAYBE_SPAN for b in refs["maybe_anims"])
    animations = [n for n in free if not near(n)]
    maybe_animations = [n for n in free if near(n)]
    free_snd = [[s.group, s.number] for s in char.sounds.sounds
                if (s.group, s.number) not in refs["sounds"] and (s.group, s.number) not in RESERVED_SOUNDS]
    sounds = [s for s in free_snd if s[0] not in refs["sound_groups"]]
    maybe_sounds = [s for s in free_snd if s[0] in refs["sound_groups"]]
    return {"sprites": sprites, "animations": animations, "sounds": sounds,
            "maybe_animations": maybe_animations, "maybe_sounds": maybe_sounds,
            "dynamic_references": len(refs["dynamic"]), "dynamic_examples": refs["dynamic"][:10],
            "notes": tr("sprites in groups 5000–5999 and 9000–9999, animations 0–199/5000–5999 and "
                        "the KO sound 11,0 belong to the engine and are not listed")}


def helper_states(statedefs: dict) -> set[int]:
    """Estados que os helpers rodam: os `stateno` literais dos controladores Helper e os estados
    a que eles levam por ChangeState/SelfState. Um estado a que o próprio char também vai (por
    um ChangeState de fora dos helpers) continua do char, a menos que seja alvo direto de Helper.
    `statedefs`: {número: StateDef}."""
    def targets(sd, kinds):
        out = set()
        for c in sd.controllers:
            if c.type.lower() in kinds:
                key = "stateno" if c.type.lower() == "helper" else "value"
                m = _INT.match((c.section.get(key) or "").split(";")[0])
                if m and int(m[1]) in statedefs:
                    out.add(int(m[1]))
        return out

    direct: set[int] = set()
    for sd in statedefs.values():
        direct |= targets(sd, ("helper",))

    def closure(blocked: set[int]) -> set[int]:
        reach, todo = set(direct), list(direct)
        while todo:
            for m in targets(statedefs[todo.pop()], ("changestate", "selfstate")) - reach - blocked:
                reach.add(m)
                todo.append(m)
        return reach

    # o caminho do helper para nos estados do char (os que estados de fora dos helpers chamam);
    # bloquear um pode soltar outros, então repete até parar de mudar
    blocked: set[int] = set()
    while True:
        reach = closure(blocked)
        from_char = set()
        for n, sd in statedefs.items():
            if n not in reach:
                from_char |= targets(sd, ("changestate", "selfstate"))
        new = from_char - direct
        if new <= blocked:
            return reach
        blocked |= new
