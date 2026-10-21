"""Guia de MUGEN para o agente: como as peças funcionam, para ele montar qualquer golpe em vez de
copiar um molde. Em inglês (lido pelo modelo). Cada tópico é curto e direto, com o porquê das
regras que mais derrubam quem escreve CNS: física, lado, empurrão entre os corpos, HitDef.
"""
from __future__ import annotations

TOPICS: dict[str, str] = {
    "states": """\
A move is a [Statedef N] header plus [State N, label] controllers, run top to bottom every tick.
Header: type = S/C/A (standing, crouching, air: what the engine and the opponent see),
movetype = A (attacking) / I / H, physics = S (stand friction) / C (crouch friction) /
A (gravity, and when y >= 0 the engine lands the player into state 52 by itself) / N (none: you move
it yourself), ctrl = 0 during a move, anim = first animation, velset = x, y applied on entering,
poweradd, juggle (air juggle points it costs), facep2 = 1 to turn toward the opponent on entering.
Triggers: lines with the same number are ANDed (trigger1 = a, trigger1 = b), different numbers are
ORed, triggerall is ANDed with all of them. A controller with no trigger1 never runs.
`persistent = 0` makes a controller run only the first time its triggers are true.
Ending: ChangeState value = 0, ctrl = 1 when the animation ends (trigger1 = AnimTime = 0) for a
standing move; 11 for crouching; an air move with physics A lands into 52 automatically.
Never reuse another move's statedef or animation number for a new move.""",

    "timing": """\
time = ticks since entering the state (0 on the first tick).
AnimElem = n is true only on the first tick of element n (1 = first frame of the animation).
AnimElemTime(n) >= 0 is true from the start of element n on; AnimElemTime(n) = 2 two ticks in.
AnimTime = 0 on the last tick of the animation (AnimTime counts up to 0 from minus the remaining time).
AnimElemNo(0) = the element shown now. Anim = N is the animation playing now.
To do something at a moment of the motion instead of a frame, test position or velocity:
`vel y > 0` (falling), `pos y > -30` (less than 30 px above the ground), `p2bodydist x < 20`.""",

    "movement": """\
Positions: x grows in the direction the player FACES, y is negative upward (pos y = -40: 40 px up).
VelSet x, y sets the velocity; VelAdd adds; VelMul multiplies; PosAdd moves instantly.
Velocities are per tick and relative to the facing: x = 4 is 4 px/tick forward.
Physics S/C slow x down by the friction constants each tick; physics N keeps it; physics A adds
gravity (const(movement.yaccel), about 0.44) to vel y each tick.
Jump math with gravity g and launch speed vy (vel y = -vy): peak height = vy*vy / (2*g); time up =
vy / g; time in the air = 2*vy / g; distance = vx * time in the air. Example: vy = 8, g = 0.44 ->
73 px high, 36 ticks in the air; vx = 3 travels 109 px.
A move that jumps from the ground: header type = A, physics = A, velset = vx, -vy, entered from a
[Statedef -1] entry with statetype != A. To change the animation in mid-air, ChangeAnim with a
trigger on time, vel y or pos y.
After the move, read the `path` of simulate_state: dx (where the character is relative to the
opponent), y, and whether the attack box is out.""",

    "sides": """\
Turn flips the facing at once. Because velocities are relative to the facing, a moving character
reverses direction after Turn: put VelMul x = -1 right BEFORE the Turn (same trigger) to keep
going the same way on screen.
p2dist x is the opponent's distance in front of the player: negative means the opponent is behind.
`trigger1 = p2dist x < 0` + Turn makes the player face the opponent again after passing it.
facep2 = 1 in the header (or a Turn) faces the opponent when the move starts.
Passing over an opponent: bodies push each other while their width boxes ([Size] ground.front,
ground.back) overlap, unless one is entirely above the other: the jumper's feet must be higher
than the opponent's head (its size.height, about 60 px; use a peak around 1.5x that) while
crossing. Time the crossing near the peak: vx = distance to the opponent / time up.
Hitting the back: after turning, the attack box points at the opponent again; land close to it
(slow the horizontal speed after the turn) so the attack reaches.""",

    "hitting": """\
HitDef defines ONE hit: it stays active until it hits (or is guarded) or the state ends. It only
connects while the player's Clsn1 (red, in the animation) touches the opponent's Clsn2 (blue).
Trigger it on the frame where the attack begins (trigger1 = AnimElem = 3) or on the tick the
attack animation starts (trigger1 = Anim = N && AnimElemTime(1) = 0).
Key parameters: attr = S/C/A (the attacker's state type), NA/SA/HA (normal, special, hyper attack)
or NT/ST/HT (throws); damage = hit, guard; guardflag: H (stand guard), L (crouch guard), M = HL,
A (air guard); air attacks use HA (an overhead), lows use L; pausetime = attacker, opponent freeze;
animtype = Light/Medium/Hard/Back/Up/DiagUp; ground.type = High/Low/Trip;
ground.velocity = x (, y) pushes the opponent (negative x = away from the attacker);
air.velocity for an opponent in the air; fall = 1 knocks down; sparkno, sparkxy (spark position
relative to the attacker); hitsound / guardsound = S5,0... (S = the common fightfx sounds).
Several hits: one HitDef per hit, each triggered at its own moment (AnimElem = 2, AnimElem = 4),
and the animation needs Clsn1 on each of those frames.
An attack box that never reaches the opponent's body whiffs: check `first_hit` in simulate_state.""",

    "projectiles": """\
Projectile controller (one per shot): projanim = flying animation, projhitanim, projremanim,
offset = x, y from the player's axis, velocity = x, y, projremovetime (-1 = until it leaves the
screen or hits), plus the hit parameters of a HitDef (attr = S, SP; damage; guardflag; pausetime;
ground.velocity...). Fire it on a frame: trigger1 = AnimElem = 3.
For effects that do not hit, use Explod (anim, pos, postype = p1, bindtime, removetime) instead.
For something with its own logic (a clone, a wave that grows), use Helper with its own statedef.""",

    "throws": """\
A throw is a HitDef with attr = S, NT, guardflag empty, hitflag = M- (can't grab someone in the air
or in hitstun), priority = 1, Miss and a short Clsn1 range, plus p1stateno = the throwing state and
p2stateno = the state the opponent is put in (p2getp1state = 1 so that state is read from your
character). In the throwing state, TargetBind holds the opponent at an offset, TargetLifeAdd /
TargetState / TargetVelSet finish the throw. Enter it from [Statedef -1] when the opponent is close:
trigger1 = p2bodydist x < 5 && (p2statetype = S || p2statetype = C) && p2movetype != H.""",

    "supers": """\
A super spends power: [Statedef -1] entry with triggerall = power >= 1000 (one bar), and
poweradd = -1000 in the header (or a PowerAdd). SuperPause (time = 30, anim, sound, darken = 1,
p2defmul) freezes the screen for the flash at the start. attr = S, HA. Specials and supers usually
also cancel a normal that hit: trigger2 = movecontact && stateno = [200, 699] in the -1 entry.""",

    "commands": """\
[Command] name = "...", command = sequence, time = ticks to enter it. Symbols: D, F, B, U and the
diagonals DF, DB, UF, UB; buttons a b c x y z s; ~ = release (~D = let go of down, ~30a = hold a
30 ticks, then release), / = hold (/F), $ = the direction or a diagonal containing it ($D), > = no
other input between two steps, + = together (x+y), comma = then.
Quarter circle forward: ~D, DF, F, x. Dragon punch: ~F, D, DF, x. Dash: F, F.
[Statedef -1] runs every tick: its ChangeState entries are tested in file order and the FIRST one
whose triggers pass wins, so specials and supers must come before the normal attacks on the same
button. Each entry: triggerall = command = "name", plus statetype and ctrl conditions.""",

    "animation": """\
[Begin Action N], then one line per frame: group, item, x offset, y offset, time [, flip [, trans]].
flip = H (mirror), V, HV; trans = A (add, for glows), S, AS. time = -1 holds the frame forever.
LoopStart before a frame makes the animation loop from it.
Collision boxes go BEFORE their frame: 'Clsn2: <count>' then that many 'Clsn2[i] = x1, y1, x2, y2'
(relative to the axis, y negative up) apply to the next frame; 'Clsn2Default: <count>' applies to
every frame without its own. Clsn2 (blue, hurtable) on every frame; Clsn1 (red, attack) only on
active frames, over the limb that hits.
Pick poses by looking at them (view_animations, view_sprite), not by number: list_animations says
what each animation is.""",
}


def topic(name: str | None) -> str:
    if not name:
        return "topics: " + ", ".join(TOPICS)
    key = name.strip().lower()
    if key not in TOPICS:
        raise KeyError(f"no topic '{name}'; topics: {', '.join(TOPICS)}")
    return TOPICS[key]
