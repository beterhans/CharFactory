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
relative to the attacker); hitsound / guardsound = S1,16 (S = the character's own .snd; without
S, the engine's fight.snd). Most characters use their own sounds and sparks: see topic style.
Several hits: one HitDef per hit, each triggered at its own moment (AnimElem = 2, AnimElem = 4),
and the animation needs Clsn1 on each of those frames.
An attack box that never reaches the opponent's body whiffs: check `first_hit` in simulate_state.""",

    "projectiles": """\
Make projectiles, beams, waves, clones and anything with its own logic with a Helper, not the
Projectile controller (helpers can move, scale, spawn effects, hit several times and be cleaned up).
Fire it from the move: Helper with helpertype = normal, stateno = its statedef, ID, pos, postype =
p1, facing = 1, ownpal = 1, supermovetime = 999, pausemovetime = 999, ignorehitpause = 1, on a
frame (trigger1 = AnimElem = 3). Its statedef: type = A, movetype = A, physics = N, a VelSet to
move it, AssertSpecial flag = noshadow, its own HitDef (pausetime = 0, N: the helper does not
freeze, the opponent does), and DestroySelf when it hit (MoveContact), when its time is up
(Time >= N or AnimTime = 0) or when it leaves the screen (FrontEdgeDist < -50). Read the
character's values from the helper with `root,` (root, facing). For effects that do not hit, use
Explod (anim, pos, postype = p1, bindtime, removetime = -2, ownpal = 1).""",

    "throws": """\
A throw is a HitDef with attr = S, NT, guardflag empty, hitflag = M- (can't grab someone in the air
or in hitstun), priority = 1, Miss and a short Clsn1 range, plus p1stateno = the throwing state and
p2stateno = the state the opponent is put in (p2getp1state = 1 so that state is read from your
character). In the throwing state, TargetBind holds the opponent at an offset, TargetLifeAdd /
TargetState / TargetVelSet finish the throw. Enter it from [Statedef -1] when the opponent is close:
trigger1 = p2bodydist x < 5 && (p2statetype = S || p2statetype = C) && p2movetype != H.""",

    "supers": """\
A super spends power: [Statedef -1] entry with triggerall = power >= 1000 (one bar) and
poweradd = -1000 in the header (-2000, -3000 for two or three bars). SuperPause at the start
freezes the screen for the flash; most characters do the flash themselves: SuperPause anim = -1,
sound = -1, darken = 0, time = 30, movetime = 30, unhittable = 1, plus their own flash (Explod or
Helper) and stage darkening (BGPalFX). attr = S, HA. Specials and supers usually also cancel a
normal that hit: trigger2 = movecontact && stateno = [200, 699] in the -1 entry. While the
character must not be hit, NotHitBy value = SCA, time = 1 runs every tick.""",

    "style": """\
How most characters are written (measured on 260 JUS-style characters). Follow it when writing by
hand, and copy the character's own values from one of its moves (get_move on a normal attack).
DO
- Helpers for projectiles, beams, clones and hit sparks (253 of 260 characters; projectiles topic).
- HitDef with the character's own sounds (hitsound = S1,16, guardsound = S4,1: S is its own .snd)
  and its own sparks: sparkno = -1 (or the S number it uses to turn the engine's off) and the spark
  made by an Explod on the hit (trigger1 = MoveHit = 1, postype = p2, ownpal = 1, removetime = -2,
  bindtime = 1, ignorehitpause = 1); guard.sparkno = S<its guard spark>.
- HitDef values that hold: guardflag = MA (HA in the air), ground.type = High, ground.slidetime =
  12, ground.hittime = 15, priority = 3, Hit, pausetime = 10,10 or 12,12 (0,N in helpers),
  fall.recover = 0 on a hit that knocks down in the middle of a combo, envshake.time = 5-20.
- Explod: postype = p1 (p2 on the opponent), ownpal = 1, removetime = -2 (or -1), bindtime = 1
  (-1 to follow the character), removeongethit = 1, supermovetime = 999, pausemovetime = 999,
  ignorehitpause = 1, trans = add/sub/addalpha for light and shadow, scale to size it.
- Header: ctrl = 0, velset = 0,0 (or a step forward), sprpriority = 2, juggle = 1 on the ground
  and 2 in the air, facep2 = 1 on ground attacks; normals gain power (poweradd = 30-100).
- Timing: Time = N for events, AnimElem = N for hits tied to a frame, AnimTime = 0 to end; end
  with ChangeState value = 0, ctrl = 1. EnvShake time = 5-20, ampl = -4..-8, freq = 60, phase = 90.
- AI: [Statedef -1] entries test AILevel (trigger2 = AILevel && random < AILevel * N).
- Numbers in the 320x240 scale (no localcoord in the .def).
DON'T
- Don't use the Projectile controller (only 13 of 260 characters do).
- Don't use the engine's sparks and sounds (sparkno = 0-3, hitsound = 5,0 from fightfx/fight.snd).
- Don't let SuperPause darken the screen or play anim 100 / sound 20,0: do the flash yourself.
- Don't use helpertype = player (232 of 27,430 helpers).
- Don't leave a helper alive or an effect running: every helper state ends in DestroySelf, effects
  have removetime and removeongethit = 1.
- Don't let effects freeze in pauses: supermovetime and pausemovetime = 999 on Explods and Helpers.
ANGLE, SYMMETRY AND COHERENCE
- Write angles for the character facing right: the engine mirrors them when it faces left
  (positive = counterclockwise, the front of the sprite goes up). Never multiply an angle by facing.
- AngleDraw lasts only the tick it runs: trigger1 = 1 (every tick), ignorehitpause = 1. To spin,
  AngleAdd value = N every tick (or AngleSet once) plus AngleDraw with no value; its scale sizes it.
- Facing follows postype: p1 -> facing = 1 (turns with the character), p2 -> facing = -1 (looks back
  at the attacker), the same for Helpers. Explod facing is already relative: no facing = facing.
- Sparks and debris vary: angle = random % 360, facing/vfacing = -1 + random % 2, and a small pos
  jitter on multi-hits; a fixed angle only for a slash that follows the swing.
- Same scale on both axes for sparks, auras and flashes (xscale = yscale); stretch one axis only
  for beams and trails, along their length.
- Keep the character's own scale system: if its Explods multiply scale by a global factor
  (.3*Helper(999999),Fvar(16) in 12,847 of them), new effects use the same factor.
- One move, one look: the hit effect sits on the attack box (postype p2, pos at the Clsn1 height),
  hits of the same weight share spark and size, the finisher is bigger; ModifyExplod (pos, scale,
  angle) animates one effect instead of stacking many; auras on a helper use BindToRoot.""",

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
