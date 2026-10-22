"""As 12 paletas de um char (as cores que o jogador escolhe na seleção) de uma vez: a paleta é
separada em faixas (as rampas de cor da pele, do cabelo, da roupa...), cada faixa pode ser
travada ou girada por conta própria e um esquema gera as outras 11 a partir da 1."""
from __future__ import annotations

import colorsys
import random

from ..formats import sff
from ..project import Character
from ..i18n import tr

HUE_NAMES = [(15, tr("red")), (40, tr("orange")), (65, tr("yellow")), (160, tr("green")), (200, tr("cyan")),
             (255, tr("blue")), (290, tr("purple")), (335, tr("pink")), (360, tr("red"))]
OUTLINE, SKIN = tr("outline/shadow"), tr("skin?")

SCHEMES = {"temas": tr("Themes: each palette a different look (shadow, gold, ice, fire, neon…)"),
           "sortear": tr("Surprise: random color harmonies (generate again for others)"),
           "arco": tr("Rainbow: the hue turns 30° on each palette"),
           "desencontrado": tr("Staggered bands: each band turns by a different step"),
           "escuro_claro": tr("Five colors and their dark versions: 2–6 colored, 7–12 darker")}


# temas das paletas 2 a 12: (nome, matiz principal, matiz de destaque, saturação ×, brilho ×,
# tinta nos brancos/cinzas). A faixa maior recebe o principal, a segunda o destaque, e assim
# alternando; os cinzas ganham a cor principal (girar o matiz de um cinza não muda nada)
THEMES = [(tr("Shadow"), 0, 275, 0.75, 0.5, 0.12), (tr("Gold"), 45, 28, 1.35, 1.05, 0.35),
          (tr("Ice"), 195, 222, 0.85, 1.18, 0.25), (tr("Toxic"), 100, 285, 1.45, 1.0, 0.3),
          (tr("Royal"), 275, 48, 1.25, 0.95, 0.25), (tr("Fire"), 10, 38, 1.45, 1.05, 0.3),
          (tr("Ocean"), 215, 170, 1.2, 0.95, 0.25), (tr("Ghost"), 200, 200, 0.08, 1.22, 0.0),
          (tr("Pastel"), 330, 175, 0.55, 1.25, 0.2), (tr("Military"), 85, 35, 0.6, 0.8, 0.2),
          (tr("Neon"), 300, 160, 1.6, 1.1, 0.45)]
HARMONIES = {tr("complementary"): (0, 180), tr("triad"): (0, 120, 240), tr("analogous"): (0, 30, -30),
             tr("split complementary"): (0, 150, 210), tr("square"): (0, 90, 180, 270)}
_NEUTRAL = (tr("white"), tr("gray"))


def _turn(target: float, band: dict) -> float:
    """Giro (graus, -180..180) que leva o matiz médio da faixa ao alvo."""
    d = (target - band["hue"] * 360) % 360
    return d - 360 if d > 180 else d


def _hls(rgb) -> tuple[float, float, float]:
    r, g, b = rgb
    return colorsys.rgb_to_hls(r / 255, g / 255, b / 255)


def used_indices(char: Character, slot: int = 1, limit: int = 5000) -> set[int]:
    """Índices que os sprites da paleta usam. Lê todos (até `limit`): os 120 primeiros de antes
    deixavam cores de golpes e efeitos de fora das faixas (45 no Jotaro), e elas não mudavam
    em nenhuma paleta gerada; decodificar centenas de sprites leva centésimos de segundo."""
    s = char.sprites
    pi = s.find_palette(1, slot)
    used: set[int] = set()
    n = 0
    for spr in s.sprites:
        if spr.palette_index == pi and not spr.is_truecolor and spr.linked_to is None:
            used |= set(s.pixels(spr))
            n += 1
            if n >= limit:
                break
    used.discard(0)
    if len(used) < 8:            # SFF v1 com paleta por sprite: vale a paleta toda
        used = {i for i, c in enumerate(s.palettes[pi].colors) if i and any(c)} if pi >= 0 else used
    return used


def name_of(hue: float, light: float, sat: float) -> str:
    if light < 0.12:
        return OUTLINE
    if sat < 0.14:
        return tr("white") if light > 0.8 else tr("gray")
    deg = hue * 360
    if 8 <= deg <= 45 and 0.18 <= sat <= 0.8 and 0.35 <= light <= 0.88:
        return SKIN
    return next(n for top, n in HUE_NAMES if deg <= top)


def ranges(colors: list, used: set[int] | None = None) -> list[dict]:
    """Faixas de cor: os índices usados agrupados pela família da cor (contorno, pele, cada
    matiz, branco, cinza). Vale para paleta em rampas e para paleta embaralhada."""
    import math
    groups: dict[str, list[int]] = {}
    for i in range(1, len(colors)):
        if used is not None and i not in used:
            continue
        h, l, sat = _hls(colors[i])
        groups.setdefault(name_of(h, l, sat), []).append(i)
    res = []
    for name, run in groups.items():
        hs = [_hls(colors[i]) for i in run]
        x = sum(math.cos(2 * math.pi * h[0]) * max(h[2], 0.01) for h in hs)
        y = sum(math.sin(2 * math.pi * h[0]) * max(h[2], 0.01) for h in hs)
        res.append({"indices": run, "hue": (math.atan2(y, x) / (2 * math.pi)) % 1,
                    "light": sum(x[1] for x in hs) / len(hs), "sat": sum(x[2] for x in hs) / len(hs),
                    "name": name,
                    # contorno e pele começam travados: quase sempre ficam iguais em todas
                    "locked": name in (OUTLINE, SKIN)})
    res.sort(key=lambda r: r["indices"][0])
    return res


def adjust(colors: list, rngs: list[dict], adj: dict[int, tuple]) -> list:
    """Cores novas: cada faixa j com (giro de matiz em graus, saturação ×, brilho ×[, saturação
    somada]). A saturação somada tinge brancos e cinzas, que só girando o matiz não mudam."""
    new = [tuple(c) for c in colors]
    for j, (dh, sm, bm, *rest) in adj.items():
        sa = rest[0] if rest else 0.0
        for i in rngs[j]["indices"]:
            h, l, s = _hls(colors[i])
            top = 1.0
            if s < 0.02 and sa:                  # cinza puro: o matiz dele é 0; o giro já leva ao alvo
                h, top = 0.0, 0.88               # e o branco puro (luz 100%) não pega cor nenhuma
            r, g, b = colorsys.hls_to_rgb((h + dh / 360) % 1, max(0.0, min(top, l * bm)),
                                          max(0.0, min(1.0, s * sm + sa)))
            new[i] = (round(r * 255), round(g * 255), round(b * 255))
    return new


def scheme(name: str, rngs: list[dict], seed: int | None = None,
           labels: dict | None = None) -> dict[int, dict[int, tuple]]:
    """Ajustes das paletas 2 a 12 (a 1 é a original) para as faixas não travadas. `labels`, se
    dado, recebe o nome de cada paleta (o tema ou a harmonia sorteada). `seed` fixa o sorteio."""
    free = [j for j, r in enumerate(rngs) if not r["locked"]]
    by_size = sorted(free, key=lambda j: -len(rngs[j]["indices"]))      # a maior faixa primeiro
    rnd = random.Random(seed)
    out = {}
    for k in range(1, 12):
        slot = k + 1
        if name == "temas":
            title, main, accent, sm, bm, tint = THEMES[k - 1]
            out[slot] = {}
            for rank, j in enumerate(by_size):
                # as faixas menores variam pouco em volta do principal/destaque (±12°): um
                # passo crescente levava a 5ª faixa do Sombrio para o amarelo
                target = (main if rank % 2 == 0 else accent) + ((rank // 2) % 3 - 1) * 12 * (rank > 1)
                neutral = rngs[j]["name"] in _NEUTRAL or rngs[j]["sat"] < 0.14
                out[slot][j] = (_turn(main if neutral else target, rngs[j]), sm, bm, tint if neutral else 0.0)
            if labels is not None:
                labels[slot] = title
        elif name == "sortear":
            title, offsets = rnd.choice(list(HARMONIES.items()))
            base = rnd.uniform(0, 360)
            sm, bm = rnd.uniform(0.85, 1.5), rnd.uniform(0.75, 1.15)
            tint = rnd.choice((0.0, 0.2, 0.35))
            out[slot] = {}
            for rank, j in enumerate(by_size):
                target = base + offsets[rank % len(offsets)] + rnd.uniform(-12, 12)
                neutral = rngs[j]["name"] in _NEUTRAL or rngs[j]["sat"] < 0.14
                out[slot][j] = (_turn(target, rngs[j]), sm, bm, tint if neutral else 0.0)
            if labels is not None:
                labels[slot] = title
        elif name == "arco":
            out[slot] = {j: (30 * k, 1.0, 1.0) for j in free}
        elif name == "desencontrado":
            out[slot] = {j: ((30 * k * (1 + n % 3) + 47 * n) % 360, 1.0, 1.0) for n, j in enumerate(free)}
        else:                                   # escuro_claro
            base = (k - 1) % 6                  # 2..6 coloridas; 7 = original escura; 8..12 = 2..6 escuras
            dark = k >= 6
            out[slot] = {j: (60 * base, 1.1 if dark else 1.0, 0.62 if dark else 1.0) for j in free}
    return out


def write(char: Character, palettes: dict[int, list]) -> dict:
    """Grava as paletas 1,n (cria as que faltam)."""
    s = char.sprites
    for slot, cols in palettes.items():
        i = s.find_palette(1, slot)
        if i >= 0:
            s.palettes[i].colors = [tuple(c) for c in cols]
        else:
            s.palettes.append(sff.Palette(1, slot, [tuple(c) for c in cols]))
    char.mark("sprites")
    return {"slots": sorted(palettes)}


def preview_image(char: Character, group: int, item: int, colors: list):
    """O sprite com estas cores, sem gravar nada."""
    s = char.sprites
    spr = s.find(group, item)
    if spr is None:
        return None
    return s.image(spr, sff.Palette(1, 0, [tuple(c) for c in colors])).convert("RGBA")


POSES = [(0, tr("standing")), (11, tr("crouching")), (41, tr("jump")), (200, tr("attack")),
         (5000, tr("hit reaction")), (180, tr("win"))]


def pose_sprites(char: Character, n: int = 6) -> list[tuple[int, int, str]]:
    """Um sprite de cada pose que o char tem (a 1ª imagem da anim; se faltar, a próxima)."""
    out = []
    for anim, label in POSES:
        a = char.anims.get(anim) if char.anims else None
        f = next((f for f in (a.frames if a else []) if f.group >= 0 and char.sprites.find(f.group, f.item)), None)
        if f is not None and (f.group, f.item) not in {(g, i) for g, i, _ in out}:
            out.append((f.group, f.item, label))
    return out[:n]


# ------------------------------------------------------------------ paletas no .def

BUTTONS = ("x", "y", "z", "a", "b", "c")
DEFAULTS_MAX = 4                          # o MUGEN lê até 4 em pal.defaults


def _ints(v: str | None) -> list[int]:
    out = []
    for part in (v or "").split(";")[0].split(","):
        try:
            out.append(int(part.strip()))
        except ValueError:
            pass
    return out


def def_mapping(char: Character) -> dict:
    """Como o .def deixa escolher as paletas: botões x..c (Start + botão = +6) e pal.defaults
    (o que o motor usa quando escolhe sozinho, e para não repetir a cor num espelho).
    {"keymap", "defaults", "existing", "unreachable", "problems"}."""
    d = char.definition
    keymap = {}
    for i, b in enumerate(BUTTONS):
        v = _ints(d.get("palette keymap", b))
        keymap[b] = v[0] if v else i + 1      # sem a linha, vale o padrão do motor (x=1 … c=6)
    defaults = _ints(d.get("info", "pal.defaults"))
    existing = sorted(p.item for p in char.sprites.palettes if p.group == 1 and 1 <= p.item <= 12)
    reach = {v for v in keymap.values()} | {v + 6 for v in keymap.values()}
    unreachable = [n for n in existing if n not in reach]
    problems = []
    if unreachable:
        problems.append(tr("the buttons in [Palette Keymap] never reach palette(s) {0}").format(
            ", ".join(map(str, unreachable))))
    if len(existing) > 1 and len({n for n in defaults if n in existing}) < min(len(existing), 2):
        problems.append(tr("pal.defaults does not list other palettes: the engine falls back to "
                           "palette 1 when it picks (CPU, random, mirror match)"))
    return {"keymap": keymap, "defaults": defaults, "existing": existing,
            "unreachable": unreachable, "problems": problems}


def fix_mapping(char: Character) -> list[str]:
    """Acerta o .def para as paletas que o SFF tem: botões x..c nas paletas 1 a 6 (Start dá
    7 a 12) se algum ficava de fora, e pal.defaults com as primeiras paletas que existem.
    Devolve o que mudou (vazio se já estava certo)."""
    m = def_mapping(char)
    changes = []
    if m["unreachable"]:
        sec = char.definition.section("Palette Keymap")
        for i, b in enumerate(BUTTONS):
            sec.set(b, str(i + 1))
        changes.append(tr("[Palette Keymap]: x, y, z, a, b, c = palettes 1 to 6 (Start + button = 7 to 12)"))
    want = m["existing"][:DEFAULTS_MAX]
    if len(m["existing"]) > 1 and [n for n in m["defaults"] if n in m["existing"]][:len(want)] != want:
        char.definition.section("Info").set("pal.defaults", ",".join(map(str, want)))
        changes.append(tr("pal.defaults = {0}").format(",".join(map(str, want))))
    if changes:
        char.mark("def")
    return changes
