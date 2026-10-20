<p align="center">
  <img src="docs/media/banner.png" alt="Char Factory: M.U.G.E.N character editor" width="100%">
</p>

<p align="center">
  <a href="../../releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/eduardovbe/CharFactory?style=flat-square&color=a6e22e&labelColor=1e1f1a"></a>
  <a href="../../actions/workflows/ci.yml"><img alt="Tests" src="https://img.shields.io/github/actions/workflow/status/eduardovbe/CharFactory/ci.yml?branch=main&style=flat-square&labelColor=1e1f1a&label=tests"></a>
  <a href="../../releases"><img alt="Downloads" src="https://img.shields.io/github/downloads/eduardovbe/CharFactory/total?style=flat-square&color=a6e22e&labelColor=1e1f1a"></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-a6e22e?style=flat-square&labelColor=1e1f1a"></a>
</p>

<p align="center">
  A free, open source editor for <b>M.U.G.E.N</b> and <b>Ikemen GO</b> characters.<br>
  Sprites, animations, collision boxes, sounds and code in one window, plus a simulator<br>
  that plays your moves tick by tick without opening the engine.
</p>

<p align="center">
  <b><a href="../../releases/latest">Download for Windows</a></b> ·
  <a href="#what-makes-it-different">What makes it different</a> ·
  <a href="#the-editors">The editors</a> ·
  <a href="#command-line">Command line</a> ·
  <a href="#development">Development</a>
  <br>
  <sub>English · Español · Português (Brasil)</sub>
</p>

## Get started

1. Download `Char-Factory-...-windows.zip` from the **[latest release](../../releases/latest)**.
2. Extract it anywhere and open **`Char Factory.exe`**. Nothing to install.
3. Open a character's `.def`, or drop a `.def`, `.zip`, `.rar` or `.7z` on the window.

The first launch asks for the language and the theme. If the character lives inside your MUGEN
folder, **Run in the engine** (<kbd>Ctrl</kbd>+<kbd>R</kbd>) finds MUGEN by itself.

## What makes it different

### Frame data, and a backup side by side

<img src="docs/media/only-compare.webp" alt="Simulator running the current version of a punch next to a backup, with frame data for both" width="100%">

<kbd>F9</kbd> runs a state tick by tick, with helpers, explods and hit pauses, and measures startup,
active and recovery frames and the advantage on hit or guard. Pick a backup in **Compare** and both
versions play side by side. P2 can stand, guard, crouch or be in the air, and moves chain into combos.

### A timeline that edits the code

<img src="docs/media/only-timeline.webp" alt="Dragging a PlaySnd on the timeline rewrites its Time trigger, and a double-click opens the controller" width="100%">

Every frame, hit, sound and effect of a move on one track. Drag a `PlaySnd` to another tick and its
`Time = N` trigger is rewritten; double-click any event to open its controller.

### Collision boxes in one click

<img src="docs/media/only-clsn.webp" alt="An empty frame gets anatomical Clsn2 boxes and then an attack Clsn1 on the extended arm" width="100%">

Anatomical Clsn2 (head, torso, legs) from the sprite's silhouette, the attack Clsn1 on an extended
limb, and boxes interpolated between two key frames.

### Command palette and go to definition

<img src="docs/media/only-command-palette.webp" alt="Typing state 1000 in the command palette and jumping to the state in the code" width="100%">

<kbd>F1</kbd> runs any command or jumps to `anim 200`, `state 1000`, `sprite 9000,0` or `sound 5,0`.
In the code, <kbd>F12</kbd> or <kbd>Ctrl</kbd>+click opens the definition under the cursor.

### And the tools around them

<table>
  <tr>
    <td width="50%" valign="top">
      <img src="docs/media/only-transplant.png" alt="Move transplant dialog listing what comes along with the move"><br>
      <b>Move transplant</b><br>
      Copies a whole move from another character, following <code>ChangeState</code>,
      <code>Helper</code> and <code>p1/p2stateno</code>, with its animations, sprites, sounds and
      command, renumbered so nothing collides.
    </td>
    <td width="50%" valign="top">
      <img src="docs/media/only-move-wizard.png" alt="Move wizard with the move settings and the generated CNS"><br>
      <b>Move wizard</b><br>
      Design a move visually (HitDef, physics, sounds, cancels, command) and watch the CNS being
      written as you edit.
    </td>
  </tr>
  <tr>
    <td valign="top">
      <img src="docs/media/only-sheet.png" alt="Sprite sheet slicer finding eight walking frames on a sheet"><br>
      <b>Sprite sheet slicer</b><br>
      Finds the background and each frame, puts the axis on the feet and builds one palette, ready
      to import.
    </td>
    <td valign="top">
      <img src="docs/media/only-palettes12.png" alt="Twelve palettes generated from color bands, previewed in several poses"><br>
      <b>12 palettes by color bands</b><br>
      Locks what must not change (skin, outline) and generates palettes 2 to 12, previewed in
      several poses.
    </td>
  </tr>
  <tr>
    <td valign="top">
      <img src="docs/media/only-pixel-editor.webp" alt="Pixel editor stepping through the standing frames with PgDn"><br>
      <b>Pixel editor on palette indices</b><br>
      <kbd>Ctrl</kbd>+<kbd>E</kbd>: selection, magic wand, outline, onion skin, and
      <kbd>PgUp</kbd>/<kbd>PgDn</kbd> through the sprites without closing it.
    </td>
    <td valign="top">
      <img src="docs/media/only-unused.png" alt="Unused resources dialog listing sprites nothing references"><br>
      <b>Unused resources</b><br>
      Sprites, animations and sounds that nothing references, ready to delete before release.
    </td>
  </tr>
</table>

## The editors

<img src="docs/media/animation.webp" alt="Animation editor playing a punch, with the timeline following each frame" width="100%">

Animations on a canvas with rulers, grid and axis, Clsn boxes drawn with the mouse, every frame on a
timeline sized by its duration, MUGEN 1.1 scale, angle and interpolation, and GIF export.

<table>
  <tr>
    <td width="50%" valign="top">
      <img src="docs/media/sprites.png" alt="Sprite editor with the palette panel"><br>
      <b>Sprites and palettes</b><br>
      Import, export and align sprites, edit palettes and ACT files, or open a sprite in an
      external editor such as Aseprite.
    </td>
    <td width="50%" valign="top">
      <img src="docs/media/code.png" alt="States editor with the state tree, syntax highlighting and the controller list"><br>
      <b>Code</b><br>
      CNS, CMD, AIR and DEF with highlighting, docs on hover, snippets and live validation; comments
      are kept when saving.
    </td>
  </tr>
  <tr>
    <td valign="top">
      <img src="docs/media/sounds.png" alt="Sound editor showing a waveform with a tick ruler"><br>
      <b>Sounds</b><br>
      Play, cut, fade and resample on a ruler measured in game ticks; imports WAV, OGG, MP3 and FLAC.
    </td>
    <td valign="top">
      <img src="docs/media/themes.webp" alt="The same editor cycling through the eight built-in themes"><br>
      <b>Themes</b><br>
      Eight built-in themes, a theme editor and <code>.xml</code> colorset import.
    </td>
  </tr>
</table>

<details>
<summary><b>Everything else</b></summary>

- **Tools:** command tester, throw creator, PalFX editor, offset viewer, `[Statedef -1]` organizer,
  variable usage list, calculator and HTML move list export.
- **Stages:** layers, properties and a preview with camera and parallax.
- **Projects:** several characters in tabs, undo and redo everywhere, automatic backup, compare with a
  backup, find and replace in every file, open and pack `.zip` files.

</details>

### Supported formats

| Format | Read | Write |
|---|:---:|:---:|
| SFF v1.01 (PCX) and v2.00/2.01 (RLE8, RLE5, LZ5, PNG) | ✓ | ✓ <sub>(not RLE5)</sub> |
| AIR, CMD, CNS, ST, DEF <sub>(comments kept)</sub> | ✓ | ✓ |
| ZSS (Ikemen GO) | ✓ | ✓ |
| SND, ACT | ✓ | ✓ |
| ZIP, RAR, 7z (archived character) | ✓ | ZIP |

## Command line

<img src="docs/media/only-cli.png" alt="Terminal running charfactory info and charfactory validate on Kung Fu Man" width="100%">

Everything the editor does to files also works from scripts or CI, no window needed:

```powershell
charfactory render kfm.def 200 out.gif    # render an animation
charfactory sim kfm.def 210 --gif         # simulate a state tick by tick
charfactory convert-sff in.sff out.sff --version 1
charfactory --help                        # every command
```

## Development

Needs Python 3.11 or newer.

```powershell
git clone https://github.com/eduardovbe/CharFactory.git
cd CharFactory
python -m venv .venv
.venv\Scripts\pip install -e ".[gui,test]"
.venv\Scripts\charfactory-gui
```

Tests, translations, building the executable and regenerating these screenshots are covered in
[CONTRIBUTING.md](CONTRIBUTING.md). Bug reports, translations and pull requests are welcome; please
follow the [Code of Conduct](CODE_OF_CONDUCT.md), and report security problems as described in
[SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE). The bundled JetBrains Mono font is under the SIL Open Font License 1.1.

<sub>Inspired by Fighter Factory. Independent project, not affiliated with Elecbyte or the Fighter
Factory authors. M.U.G.E.N is a trademark of Elecbyte. The screenshots show Kung Fu Man, the sample
character that ships with M.U.G.E.N.</sub>
