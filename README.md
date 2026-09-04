# Classroom Jeopardy

A self-contained, server-rendered Jeopardy-style game for the classroom.
Runs on plain Python 3 (standard library `http.server`) plus `matplotlib`
for LaTeX rendering — no Flask, no internet connection required once
installed, and no external LaTeX distribution needed. Designed to run
reliably on a Chromebook / Chrome OS device (laptop or touchscreen panel)
and be driven from Chrome.

## What you get

- **Game board** (`/`) — the display/control screen. Click a dollar-value
  tile to open a question, reveal the answer, then mark which team
  answered and whether they were right or wrong. Handles Daily Double
  wagers. Switch between the Jeopardy round, Double Jeopardy round, and
  Final Jeopardy. Team scores, add/rename/remove teams, and a Reset
  button (scores only, board only, or a full reset).
- **Question editor** (`/editor`) — add/edit/delete categories and
  questions per round, mark any question as a Daily Double, and see a
  live LaTeX preview as you type. Everything is saved to a local SQLite
  database (`jeopardy.db`) sitting next to the script.
- **LaTeX rendering** — write math as `$x^2 + 1$` (inline) or
  `$$\int_0^1 x\,dx$$` (display) anywhere in a question or answer. The
  server renders it to a small PNG on the fly (via matplotlib's mathtext
  engine) and the browser fetches it dynamically — no client-side LaTeX
  library needed. This covers standard math notation, Greek letters,
  fractions, exponents, roots, etc. It does **not** support chemistry-only
  packages like `mhchem` (`\ce{...}`) — write chemical formulas using
  plain sub/superscripts instead, e.g. `$H_2O$`, `$CO_2$`, `$2H_2 + O_2 \rightarrow 2H_2O$`.

## Requirements

- Python 3.9+
- `matplotlib` (only needed for LaTeX rendering)

Install the one dependency:

```bash
pip3 install -r requirements.txt
```

## First-time setup

```bash
cd jeopardy
python3 init_db.py
```

This creates `jeopardy.db` in the same folder and seeds it with sample
categories/questions (math, chemistry, history, physics, biology,
literature, geography, calculus, plus a Final Jeopardy question) so you
can try the game immediately. Edit or delete these from the Question
Editor, or wipe everything and start blank:

```bash
python3 init_db.py --wipe
```

## Running

```bash
python3 server.py
```

Then, in Chrome:

- Game board: `http://localhost:8000/`
- Question editor: `http://localhost:8000/editor`

Leave the terminal window running — it's a lightweight local web server
and there's nothing else to start. To run it on a different port or let
other devices on the same network reach it, use environment variables:

```bash
PORT=9000 python3 server.py
```

To view the board on a second device (e.g. a Chrome OS touchscreen TV)
on the same Wi-Fi/LAN, find the host machine's local IP address and open
`http://<that-ip>:8000/` in Chrome on the TV, while running the server on
the host machine.

### Environment variables

| Variable       | Default                        | Purpose                              |
|----------------|---------------------------------|---------------------------------------|
| `PORT`         | `8000`                          | Port the server listens on            |
| `JEOPARDY_HOST`| `0.0.0.0`                       | Network interface to bind             |
| `JEOPARDY_DB`  | `jeopardy.db` next to server.py | Path to the SQLite database file      |

## Running the game

1. Open the **Question Editor** first and build out your board: pick a
   round tab (Jeopardy / Double Jeopardy / Final Jeopardy), add
   categories, and add questions with a point value, the clue, the
   answer, and whether it's a Daily Double. Everything autosaves as you
   type (a "Saved" toast confirms it).
2. Open the **Game Board**. Add/rename teams along the top scoreboard.
3. Click a tile to open a clue. If it's a Daily Double, first pick which
   team found it and enter their wager, then reveal the question.
4. Click **Reveal Answer** when ready, tap the team that answered, then
   **Correct** or **Wrong** — the score updates immediately and the tile
   greys out.
5. Use the round buttons at the top to move to Double Jeopardy or Final
   Jeopardy when ready.
6. Use **Reset Game** at any point: reset just the scores, just re-cover
   the board (keep scores), or fully reset both.

## Notes on design choices

- **No client-side framework** — plain HTML/CSS/JS talking to a small
  JSON API, so it's fast and robust on modest classroom hardware.
- **No external LaTeX installation** — matplotlib's built-in mathtext
  renderer avoids needing a multi-hundred-MB TeX distribution on a
  Chromebook; rendered PNGs are cached on disk in `latex_cache/` so
  repeat views are instant.
- **Responsive layout** — the board grid, scoreboard, and modal all use
  CSS `clamp()`/flex/grid so the same page works on a laptop screen or a
  large touchscreen panel; buttons are sized for touch (44px minimum).
- **SQLite in the same directory** — `jeopardy.db` is a single file you
  can back up, copy to build next semester's game, or swap out per class.

## File layout

```
jeopardy/
  server.py            # HTTP server + JSON API + LaTeX rendering
  init_db.py            # one-time DB setup / reseed script
  schema.sql            # table definitions
  requirements.txt
  jeopardy.db            # created on first run (your game data)
  latex_cache/           # created on first run (cached rendered PNGs)
  static/
    game.html            # game board page
    editor.html           # question editor page
    css/style.css
    js/common.js          # shared fetch + LaTeX-rendering helpers
    js/game.js             # game board logic
    js/editor.js            # editor logic
```
