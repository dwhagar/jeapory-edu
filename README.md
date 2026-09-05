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
  database in `db/` next to the script (see **Environment variables**
  below to use more than one, e.g. one per class period).
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
can try the game immediately. The first time you run `server.py` it moves
this file into `db/` automatically. Edit or delete the sample questions
from the Question Editor, or wipe everything and start blank:

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
and there's nothing else to start. To run it on a different port, use
environment variables:

```bash
PORT=9000 python3 server.py
```

If you're on a Chromebook, see **[One-click setup on a Chromebook](#one-click-setup-on-a-chromebook-linuxcrostini)**
below for a way to skip the terminal entirely after the first setup.

### Environment variables

| Variable           | Default                        | Purpose                                                                 |
|--------------------|----------------------------------|--------------------------------------------------------------------------|
| `PORT`             | `8000`                          | Port the server listens on                                              |
| `JEOPARDY_HOST`    | `127.0.0.1`                     | Network interface to bind (`0.0.0.0` to allow other devices to connect) |
| `JEOPARDY_DB_DIR`  | `db/` next to server.py         | Directory holding the sqlite database files, one per class/game         |
| `JEOPARDY_DB_NAME` | (resumes last-used database)   | Name of the database to activate at startup, creating it if needed; skips the "choose a database" prompt on load |

## One-click setup on a Chromebook (Linux/Crostini)

Chrome OS can only run Python (and matplotlib) inside its built-in Linux
environment, so this uses that to install a real launcher icon in your
Chromebook's app launcher — no terminal needed for day-to-day use once
it's set up.

**1. Check that Linux is available.** Open Chrome OS **Settings > Advanced
> Developer**, and turn on **Linux development environment** if it isn't
already. If the option is missing or greyed out, your Chromebook is
managed by a school/organization admin policy that blocks it — see
[No Linux available?](#no-linux-available-viewing-on-a-second-device) below
for a workaround that needs no setup on the Chromebook at all.

**2. Open a Linux terminal** (from the Chromebook app launcher, search for
"Terminal") and get a copy of this project, e.g.:

```bash
git clone <this repository's URL> jeopardy
cd jeopardy
```

**3. Run the installer once:**

```bash
./install.sh
```

This installs `matplotlib`, creates and seeds the database if needed, and
registers a **Classroom Jeopardy** entry in your Chromebook's app launcher.
It's safe to re-run any time, e.g. after pulling an update.

**Daily use:** open the Chromebook app launcher and click **Classroom
Jeopardy**. It starts the server if it isn't already running and opens the
game board in Chrome. When you're done for the day, use the **Exit** button
in the game board itself to stop the server (closing the browser window on
its own leaves the server running quietly in the background, ready for next
time).

If the launcher icon doesn't open a browser window, run
`xdg-mime query default x-scheme-handler/http` in the Linux terminal — it
should print `garcon_host_browser.desktop`. If it prints something else,
Linux's default web-link handler has been changed on your device; resetting
it to `garcon_host_browser.desktop` (or reinstalling Linux from Chrome OS
Settings) should fix it.

## No Linux available? (viewing on a second device)

If Linux is blocked on your Chromebook(s), run the server on any other
machine on the same Wi-Fi/network that *can* run Python 3 (a personal
laptop, a lab computer) with `JEOPARDY_HOST` set so other devices can reach
it:

```bash
JEOPARDY_HOST=0.0.0.0 python3 server.py
```

Then find that machine's local IP address and open `http://<that-ip>:8000/`
in Chrome on any Chromebook (Linux or not) or other device on the same
network — no packaging or Linux needed on the Chromebook side at all.

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
- **SQLite databases in `db/`** — each is a single file you can back up,
  copy to build next semester's game, or swap between with the in-app
  database picker (e.g. one file per class period).

## File layout

```
jeopardy/
  server.py                    # HTTP server + JSON API + LaTeX rendering
  init_db.py                   # one-time DB setup / reseed script
  sqlite_helper.py             # shared SQLite helpers used by both scripts above
  schema.sql                   # table definitions
  requirements.txt
  install.sh                   # Chromebook: one-time app-launcher setup
  launch_app.sh                # Chromebook: click target for the app launcher
  jeopardy.desktop.template    # Chromebook: app-launcher entry template
  make_icon.py                 # regenerates static/icon.png (dev-only)
  db/                          # created on first run (your game data, one .db per class/game)
  latex_cache/                 # created on first run (cached rendered PNGs)
  static/
    game.html                  # game board page
    editor.html                 # question editor page
    icon.png                    # app icon / favicon
    css/style.css
    js/common.js                # shared fetch + LaTeX-rendering helpers
    js/game.js                   # game board logic
    js/editor.js                  # editor logic
```
