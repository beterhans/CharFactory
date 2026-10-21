# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- MCP server built into the editor: Claude Code, Claude Desktop, Codex, Gemini CLI, Cursor and other
  MCP clients can read and edit the open character (states, commands, animations, constants,
  sprites, simulator frame data), with every change undoable. Local only (`127.0.0.1`) and
  protected by a token; set up in **AI → Connect an agent (MCP)**. Agents get a guide to how
  MUGEN works (physics, sides, HitDef, projectiles, throws, commands) so they can write any move,
  a one-call starting point for a new attack, animations with boxes fitted to each sprite, a
  contact sheet and names for every animation, the simulator's path (where the character goes and
  from which side a move hits), a test of which state an input reaches, the controller reference,
  and checks that refuse AIR boxes the parser would drop, inputs another move already uses and
  overwriting an existing move by accident. `get_move` shows a move's statedef, animations, input
  and the states that chain into it in one call; `edit_state` and `edit_animation` change single
  parameters, frames, timing or boxes in place instead of rewriting the whole block. State and
  animation lists are one line each with filters, and repeated problems come grouped, so a large
  character costs a fraction of the tokens.
- AI assistant panel (Ctrl+Shift+A) with the same tools, using an Anthropic, OpenAI or Google
  Gemini API key, or a local model through an OpenAI-compatible endpoint (Ollama, LM Studio,
  OpenRouter). API keys are stored in the Windows Credential Manager. Each message tells the model
  what you are looking at (the statedef under the cursor, the animation and frame, the sprite or
  the simulated state), and Claude runs with prompt caching and adaptive thinking. The panel shows
  each step in plain words (click one for what was sent and returned), images you can enlarge, what
  the AI changed at the end of each answer, and errors that say what to do, with **Try again**.
- `charfactory mcp [char.def]`: the MCP server over stdio, connected to the open window when its
  server is on; the executable accepts `--mcp` for the same.

### Fixed

- A move made in the Move Wizard went to the end of `[Statedef -1]`, where a normal attack on the
  same button took the input first and the move never came out; it now goes right before that
  entry. Its controllers are also numbered after the statedef instead of `[State 0, …]`.
- The move transplant summary showed "comandos" untranslated in every language.

## [0.1.0] - 2026-10-20

### Added

- First public release: sprite, palette, animation, sound and code (CNS, CMD, AIR, DEF) editors,
  tick-by-tick move simulator, stage editor, tools and the `charfactory` command line.
- Interface in English, Spanish and Brazilian Portuguese.

[Unreleased]: https://github.com/eduardovbe/CharFactory/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/eduardovbe/CharFactory/releases/tag/v0.1.0
