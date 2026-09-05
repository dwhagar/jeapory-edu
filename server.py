#!/usr/bin/env python3
"""
Jeopardy-style classroom game server.

Pure standard-library HTTP server (no Flask/Django needed) so it runs
reliably on a Chromebook / Chrome OS device with nothing more than
Python 3 and matplotlib installed. All game state lives in a local
SQLite database file next to this script.

Run:
    python3 server.py
Environment variables:
    PORT           - port to listen on (default 8000)
    JEOPARDY_DB_DIR - directory holding the sqlite database files, one per
                     class/game (default: db/ next to this script)
    JEOPARDY_HOST  - host/interface to bind (default 127.0.0.1)

Then open Chrome to:
    http://localhost:8000/           -> game board (teacher-facing / display)
    http://localhost:8000/editor     -> question editor
"""
import io
import json
import os
import re
import shutil
import sqlite3
import sys
import hashlib
import mimetypes
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
CACHE_DIR = BASE_DIR / "latex_cache"
CACHE_DIR.mkdir(exist_ok=True)

DB_DIR = Path(os.environ.get("JEOPARDY_DB_DIR", str(BASE_DIR / "db")))
DB_DIR.mkdir(exist_ok=True)
DEFAULT_DB_NAME = "jeopardy.db"

PORT = int(os.environ.get("PORT", "8000"))
HOST = os.environ.get("JEOPARDY_HOST", "127.0.0.1")

DB_LOCK = threading.Lock()

# ---------------------------------------------------------------------------
# Multiple named databases live in DB_DIR, one sqlite file per class/game,
# so a teacher can build one game and reuse it (via "Save As") for several
# class periods without their scores/progress colliding. The "active" file
# is whichever one every request currently reads/writes; it persists across
# restarts via ACTIVE_FILE.
# ---------------------------------------------------------------------------
ACTIVE_FILE = DB_DIR / ".active"
DB_NAME_RE = re.compile(r"^[A-Za-z0-9 _-]{1,64}$")

_active_db_lock = threading.Lock()
_active_db_name = DEFAULT_DB_NAME


def _migrate_legacy_db():
    """Pick up a pre-existing jeopardy.db from before the db/ dir existed."""
    legacy = BASE_DIR / "jeopardy.db"
    target = DB_DIR / DEFAULT_DB_NAME
    if legacy.exists() and not target.exists():
        shutil.move(str(legacy), str(target))


def _load_initial_active_name():
    if ACTIVE_FILE.exists():
        name = ACTIVE_FILE.read_text(encoding="utf-8").strip()
        if name and (DB_DIR / name).exists():
            return name
    return DEFAULT_DB_NAME


def sanitize_db_name(name):
    name = (name or "").strip()
    if not name.lower().endswith(".db"):
        name = f"{name}.db"
    stem = name[:-3]
    if not DB_NAME_RE.match(stem):
        raise ValueError(
            "Database names may only use letters, numbers, spaces, - and _ (1-64 characters)"
        )
    return name


def list_databases():
    return sorted(p.name for p in DB_DIR.glob("*.db"))


def get_active_db_name():
    with _active_db_lock:
        return _active_db_name


def get_active_db_path():
    return DB_DIR / get_active_db_name()


def set_active_db_name(name):
    global _active_db_name
    with _active_db_lock:
        _active_db_name = name
    ACTIVE_FILE.write_text(name, encoding="utf-8")

# ---------------------------------------------------------------------------
# Single-level undo: each reversible action registers a human-readable label
# and a no-arg callback that restores the previous state. Only the most
# recent action can be undone (no redo, no multi-step history).
# ---------------------------------------------------------------------------
UNDO_LOCK = threading.Lock()
_last_action = {"label": None, "revert": None}


def set_undo(label, revert):
    with UNDO_LOCK:
        _last_action["label"] = label
        _last_action["revert"] = revert


def pop_undo():
    with UNDO_LOCK:
        label = _last_action["label"]
        revert = _last_action["revert"]
        _last_action["label"] = None
        _last_action["revert"] = None
    return label, revert


def peek_undo_label():
    with UNDO_LOCK:
        return _last_action["label"]


def _revert_mark(qid, team_id, previous_score):
    with DB_LOCK:
        conn = get_db()
        try:
            conn.execute("UPDATE teams SET score=? WHERE id=?", (previous_score, team_id))
            conn.execute("UPDATE questions SET used=0 WHERE id=?", (qid,))
            conn.commit()
        finally:
            conn.close()


def _revert_team_state(team_id, name, score):
    with DB_LOCK:
        conn = get_db()
        try:
            conn.execute("UPDATE teams SET name=?, score=? WHERE id=?", (name, score, team_id))
            conn.commit()
        finally:
            conn.close()


def _revert_add_team(team_id):
    with DB_LOCK:
        conn = get_db()
        try:
            conn.execute("DELETE FROM teams WHERE id=?", (team_id,))
            conn.commit()
        finally:
            conn.close()


def _revert_delete_team(row_vals):
    with DB_LOCK:
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO teams (id, name, score, position) VALUES (?, ?, ?, ?)",
                (row_vals["id"], row_vals["name"], row_vals["score"], row_vals["position"]),
            )
            conn.commit()
        finally:
            conn.close()


def _revert_teams_snapshot(rows):
    with DB_LOCK:
        conn = get_db()
        try:
            conn.execute("DELETE FROM teams")
            for r in rows:
                conn.execute(
                    "INSERT INTO teams (id, name, score, position) VALUES (?, ?, ?, ?)",
                    (r["id"], r["name"], r["score"], r["position"]),
                )
            conn.commit()
        finally:
            conn.close()


def _revert_round(previous_round):
    with DB_LOCK:
        conn = get_db()
        try:
            set_meta(conn, "current_round", previous_round)
            conn.commit()
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# LaTeX rendering (matplotlib mathtext -> PNG). No external LaTeX install
# required, which keeps this reliable on a bare Chrome OS / Linux box.
# ---------------------------------------------------------------------------
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RENDER_LOCK = threading.Lock()


def render_latex_png(tex: str, display: bool, color: str = "#FFFFFF") -> bytes:
    """Render a math expression to a transparent PNG and cache it on disk."""
    fontsize = 34 if display else 26
    key = f"{tex}|{display}|{color}|{fontsize}"
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()
    cache_path = CACHE_DIR / f"{h}.png"
    if cache_path.exists():
        return cache_path.read_bytes()

    expr = tex.strip()
    if not expr:
        expr = r"\,"
    wrapped = f"${expr}$"

    with RENDER_LOCK:
        fig = plt.figure(figsize=(0.1, 0.1))
        try:
            txt = fig.text(0, 0, wrapped, fontsize=fontsize, color=color)
            fig.canvas.draw()
            bbox = txt.get_window_extent()
            width_in = max(bbox.width / fig.dpi, 0.05) + 0.15
            height_in = max(bbox.height / fig.dpi, 0.05) + 0.15
            fig.set_size_inches(width_in, height_in)
            fig.clf()
            fig.text(0.5, 0.5, wrapped, fontsize=fontsize, color=color,
                      ha="center", va="center")
            buf = io.BytesIO()
            fig.savefig(buf, format="png", transparent=True, dpi=150,
                        bbox_inches=None)
            data = buf.getvalue()
        except Exception:
            # Fall back to rendering the raw text (with a visible marker)
            # so a LaTeX typo doesn't break the whole question.
            fig.clf()
            fig.set_size_inches(3, 0.6)
            fig.text(0.5, 0.5, f"[LaTeX error: {expr}]", fontsize=14,
                      color="#FF6666", ha="center", va="center")
            buf = io.BytesIO()
            fig.savefig(buf, format="png", transparent=True, dpi=150)
            data = buf.getvalue()
        finally:
            plt.close(fig)

    cache_path.write_bytes(data)
    return data


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(str(get_active_db_path()), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_db_at(path):
    """Create schema + default teams at `path` if it doesn't already exist."""
    if not path.exists():
        conn = sqlite3.connect(str(path), timeout=10)
        try:
            with open(BASE_DIR / "schema.sql") as f:
                conn.executescript(f.read())
            conn.execute(
                "INSERT OR IGNORE INTO game_meta (key, value) VALUES ('current_round', '1')"
            )
            conn.execute(
                "INSERT INTO teams (name, score, position) VALUES ('Team 1', 0, 0)"
            )
            conn.execute(
                "INSERT INTO teams (name, score, position) VALUES ('Team 2', 0, 1)"
            )
            conn.commit()
        finally:
            conn.close()


def ensure_active_db():
    ensure_db_at(get_active_db_path())


def get_meta(conn, key, default=None):
    row = conn.execute("SELECT value FROM game_meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn, key, value):
    conn.execute(
        "INSERT INTO game_meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


# ---------------------------------------------------------------------------
# JSON helpers / row serialization
# ---------------------------------------------------------------------------
def row_to_dict(row):
    return {k: row[k] for k in row.keys()}


def team_to_json(row):
    return {"id": row["id"], "name": row["name"], "score": row["score"],
            "position": row["position"]}


def question_to_json_public(row):
    """Board-view question: no text revealed yet."""
    return {
        "id": row["id"],
        "value": row["value"],
        "used": bool(row["used"]),
        "is_daily_double": bool(row["is_daily_double"]),
    }


def question_to_json_full(row, category_name):
    return {
        "id": row["id"],
        "category": category_name,
        "value": row["value"],
        "question_text": row["question_text"],
        "answer_text": row["answer_text"],
        "is_daily_double": bool(row["is_daily_double"]),
        "used": bool(row["used"]),
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "JeopardyServer/1.0"

    # ---- low level helpers -------------------------------------------------
    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, data, content_type, cache_seconds=0):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if cache_seconds:
            self.send_header("Cache-Control", f"public, max-age={cache_seconds}")
        else:
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_error_json(self, message, status=400):
        self._send_json({"error": message}, status=status)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # ---- routing -------------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        try:
            if path == "/":
                return self._serve_static("game.html")
            if path == "/editor":
                return self._serve_static("editor.html")
            if path.startswith("/static/"):
                return self._serve_static(path[len("/static/"):])
            if path == "/api/render":
                return self._api_render(qs)
            if path == "/api/board":
                return self._api_board(qs)
            if path == "/api/rounds":
                return self._api_rounds()
            if path.startswith("/api/question/"):
                qid = path.rsplit("/", 1)[-1]
                return self._api_get_question(qid)
            if path == "/api/teams":
                return self._api_get_teams()
            if path == "/api/undo":
                return self._api_get_undo()
            if path == "/api/databases":
                return self._api_list_databases()
            if path == "/api/admin/categories":
                return self._api_admin_get_categories(qs)
            self._send_error_json("Not found", 404)
        except (ValueError, TypeError) as e:
            self._send_error_json(str(e), 400)
        except Exception:
            traceback.print_exc()
            self._send_error_json("Internal server error", 500)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            body = self._read_json_body()
            if path == "/api/teams":
                return self._api_add_team(body)
            if path.startswith("/api/teams/") and path.endswith("/score"):
                team_id = path.split("/")[3]
                return self._api_adjust_score(team_id, body)
            if path.startswith("/api/question/") and path.endswith("/mark"):
                qid = path.split("/")[3]
                return self._api_mark_question(qid, body)
            if path == "/api/round":
                return self._api_set_round(body)
            if path == "/api/undo":
                return self._api_post_undo()
            if path == "/api/databases":
                return self._api_create_database(body)
            if path == "/api/databases/select":
                return self._api_select_database(body)
            if path == "/api/reset/scores":
                return self._api_reset_scores()
            if path == "/api/reset/teams":
                return self._api_reset_teams()
            if path == "/api/reset/board":
                return self._api_reset_board()
            if path == "/api/reset/full":
                return self._api_reset_full()
            if path == "/api/admin/categories":
                return self._api_admin_add_category(body)
            if path == "/api/admin/questions":
                return self._api_admin_add_question(body)
            if path == "/api/exit":
                return self._api_exit()
            self._send_error_json("Not found", 404)
        except (ValueError, TypeError) as e:
            self._send_error_json(str(e), 400)
        except Exception:
            traceback.print_exc()
            self._send_error_json("Internal server error", 500)

    def do_PUT(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            body = self._read_json_body()
            if path.startswith("/api/teams/"):
                team_id = path.rsplit("/", 1)[-1]
                return self._api_update_team(team_id, body)
            if path.startswith("/api/admin/categories/"):
                cat_id = path.rsplit("/", 1)[-1]
                return self._api_admin_update_category(cat_id, body)
            if path.startswith("/api/admin/questions/"):
                qid = path.rsplit("/", 1)[-1]
                return self._api_admin_update_question(qid, body)
            self._send_error_json("Not found", 404)
        except (ValueError, TypeError) as e:
            self._send_error_json(str(e), 400)
        except Exception:
            traceback.print_exc()
            self._send_error_json("Internal server error", 500)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path.startswith("/api/teams/"):
                team_id = path.rsplit("/", 1)[-1]
                return self._api_delete_team(team_id)
            if path.startswith("/api/admin/categories/"):
                cat_id = path.rsplit("/", 1)[-1]
                return self._api_admin_delete_category(cat_id)
            if path.startswith("/api/admin/questions/"):
                qid = path.rsplit("/", 1)[-1]
                return self._api_admin_delete_question(qid)
            self._send_error_json("Not found", 404)
        except (ValueError, TypeError) as e:
            self._send_error_json(str(e), 400)
        except Exception:
            traceback.print_exc()
            self._send_error_json("Internal server error", 500)

    # ---- static file serving -------------------------------------------
    def _serve_static(self, rel_path):
        rel_path = rel_path.split("?")[0]
        target = (STATIC_DIR / rel_path).resolve()
        if STATIC_DIR not in target.parents and target != STATIC_DIR:
            return self._send_error_json("Forbidden", 403)
        if not target.exists() or not target.is_file():
            return self._send_error_json("Not found", 404)
        ctype, _ = mimetypes.guess_type(str(target))
        ctype = ctype or "application/octet-stream"
        self._send_bytes(target.read_bytes(), ctype, cache_seconds=60)

    # ---- LaTeX render endpoint ------------------------------------------
    MAX_TEX_LENGTH = 400

    def _api_render(self, qs):
        tex = (qs.get("tex", [""])[0])[: self.MAX_TEX_LENGTH]
        display = qs.get("display", ["0"])[0] == "1"
        color = qs.get("color", ["#FFFFFF"])[0]
        if not re.match(r"^#[0-9A-Fa-f]{3,8}$", color):
            color = "#FFFFFF"
        data = render_latex_png(tex, display, color)
        self._send_bytes(data, "image/png", cache_seconds=31536000)

    # ---- board / rounds ---------------------------------------------------
    def _api_rounds(self):
        with DB_LOCK:
            conn = get_db()
            try:
                current = get_meta(conn, "current_round", "1")
                rows = conn.execute(
                    "SELECT DISTINCT round FROM categories ORDER BY round"
                ).fetchall()
                rounds = [r["round"] for r in rows]
            finally:
                conn.close()
        self._send_json({"current_round": int(current), "available_rounds": rounds})

    def _api_set_round(self, body):
        round_num = body.get("round")
        if round_num is None:
            return self._send_error_json("round is required")
        with DB_LOCK:
            conn = get_db()
            try:
                previous_round = get_meta(conn, "current_round", "1")
                set_meta(conn, "current_round", int(round_num))
                conn.commit()
            finally:
                conn.close()
        set_undo("the round change", lambda: _revert_round(previous_round))
        self._send_json({"ok": True})

    def _api_board(self, qs):
        round_num = qs.get("round", [None])[0]
        with DB_LOCK:
            conn = get_db()
            try:
                if round_num is None:
                    round_num = get_meta(conn, "current_round", "1")
                round_num = int(round_num)
                cats = conn.execute(
                    "SELECT * FROM categories WHERE round=? ORDER BY position, id",
                    (round_num,),
                ).fetchall()
                board = []
                for cat in cats:
                    qs_rows = conn.execute(
                        "SELECT * FROM questions WHERE category_id=? ORDER BY position, value",
                        (cat["id"],),
                    ).fetchall()
                    board.append({
                        "id": cat["id"],
                        "name": cat["name"],
                        "questions": [question_to_json_public(q) for q in qs_rows],
                    })
            finally:
                conn.close()
        self._send_json({"round": round_num, "categories": board})

    def _api_get_question(self, qid):
        with DB_LOCK:
            conn = get_db()
            try:
                q = conn.execute("SELECT * FROM questions WHERE id=?", (qid,)).fetchone()
                if not q:
                    return self._send_error_json("Question not found", 404)
                cat = conn.execute(
                    "SELECT name FROM categories WHERE id=?", (q["category_id"],)
                ).fetchone()
                cat_name = cat["name"] if cat else ""
            finally:
                conn.close()
        self._send_json(question_to_json_full(q, cat_name))

    def _api_mark_question(self, qid, body):
        team_id = body.get("team_id")
        correct = body.get("correct")
        wager = body.get("wager")  # optional override for daily-double/points
        if team_id is None or correct is None:
            return self._send_error_json("team_id and correct are required")
        with DB_LOCK:
            conn = get_db()
            try:
                q = conn.execute("SELECT * FROM questions WHERE id=?", (qid,)).fetchone()
                if not q:
                    return self._send_error_json("Question not found", 404)
                if q["used"]:
                    return self._send_error_json("This question was already answered", 409)
                team = conn.execute("SELECT * FROM teams WHERE id=?", (team_id,)).fetchone()
                if not team:
                    return self._send_error_json("Team not found", 404)
                if wager not in (None, ""):
                    points = int(wager)
                    if points < 0:
                        return self._send_error_json("Wager cannot be negative")
                else:
                    points = int(q["value"])
                delta = points if correct else -points
                previous_score = team["score"]
                team_name = team["name"]
                conn.execute(
                    "UPDATE teams SET score = score + ? WHERE id=?", (delta, team_id)
                )
                conn.execute("UPDATE questions SET used=1 WHERE id=?", (qid,))
                conn.commit()
                new_team = conn.execute("SELECT * FROM teams WHERE id=?", (team_id,)).fetchone()
            finally:
                conn.close()
        set_undo(
            f"marking that question for {team_name}",
            lambda: _revert_mark(qid, team_id, previous_score),
        )
        self._send_json({"ok": True, "team": team_to_json(new_team)})

    # ---- undo -------------------------------------------------------
    def _api_get_undo(self):
        self._send_json({"label": peek_undo_label()})

    def _api_post_undo(self):
        label, revert = pop_undo()
        if not revert:
            return self._send_error_json("Nothing to undo", 404)
        revert()
        self._send_json({"ok": True, "label": label})

    # ---- databases -----------------------------------------------------
    def _api_list_databases(self):
        self._send_json({"databases": list_databases(), "current": get_active_db_name()})

    def _api_create_database(self, body):
        """Editor-only "Save As": copy the active database's questions into
        a new named file, reset to a fresh unplayed state, and switch to it."""
        name = sanitize_db_name(body.get("name"))
        path = DB_DIR / name
        if path.exists():
            return self._send_error_json("A database with that name already exists", 409)
        with DB_LOCK:
            source = get_active_db_path()
            if source.exists():
                shutil.copy2(source, path)
                conn = sqlite3.connect(str(path), timeout=10)
                try:
                    conn.execute("UPDATE questions SET used=0")
                    conn.execute("DELETE FROM teams")
                    conn.execute("INSERT INTO teams (name, score, position) VALUES ('Team 1', 0, 0)")
                    conn.execute("INSERT INTO teams (name, score, position) VALUES ('Team 2', 0, 1)")
                    conn.execute(
                        "INSERT INTO game_meta (key, value) VALUES ('current_round', '1') "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
                    )
                    conn.commit()
                finally:
                    conn.close()
            else:
                ensure_db_at(path)
            set_active_db_name(name)
        pop_undo()
        self._send_json({"ok": True, "current": name})

    def _api_select_database(self, body):
        name = sanitize_db_name(body.get("name"))
        path = DB_DIR / name
        if not path.exists():
            return self._send_error_json("Database not found", 404)
        with DB_LOCK:
            ensure_db_at(path)
            set_active_db_name(name)
        pop_undo()
        self._send_json({"ok": True, "current": name})

    # ---- teams -------------------------------------------------------
    def _api_get_teams(self):
        with DB_LOCK:
            conn = get_db()
            try:
                rows = conn.execute(
                    "SELECT * FROM teams ORDER BY position, id"
                ).fetchall()
            finally:
                conn.close()
        self._send_json({"teams": [team_to_json(r) for r in rows]})

    def _api_add_team(self, body):
        name = (body.get("name") or "").strip() or "New Team"
        with DB_LOCK:
            conn = get_db()
            try:
                pos_row = conn.execute("SELECT COALESCE(MAX(position), -1) AS m FROM teams").fetchone()
                pos = pos_row["m"] + 1
                cur = conn.execute(
                    "INSERT INTO teams (name, score, position) VALUES (?, 0, ?)", (name, pos)
                )
                conn.commit()
                row = conn.execute("SELECT * FROM teams WHERE id=?", (cur.lastrowid,)).fetchone()
            finally:
                conn.close()
        set_undo(f"adding {row['name']}", lambda: _revert_add_team(row["id"]))
        self._send_json({"team": team_to_json(row)})

    def _api_update_team(self, team_id, body):
        name = body.get("name")
        score = body.get("score")
        with DB_LOCK:
            conn = get_db()
            try:
                prev = conn.execute("SELECT * FROM teams WHERE id=?", (team_id,)).fetchone()
                if not prev:
                    return self._send_error_json("Team not found", 404)
                if name is not None:
                    conn.execute("UPDATE teams SET name=? WHERE id=?", (name.strip() or "Team", team_id))
                if score is not None:
                    conn.execute("UPDATE teams SET score=? WHERE id=?", (int(score), team_id))
                conn.commit()
                row = conn.execute("SELECT * FROM teams WHERE id=?", (team_id,)).fetchone()
            finally:
                conn.close()
        set_undo(
            f"changes to {prev['name']}",
            lambda: _revert_team_state(team_id, prev["name"], prev["score"]),
        )
        self._send_json({"team": team_to_json(row)})

    def _api_delete_team(self, team_id):
        with DB_LOCK:
            conn = get_db()
            try:
                row = conn.execute("SELECT * FROM teams WHERE id=?", (team_id,)).fetchone()
                conn.execute("DELETE FROM teams WHERE id=?", (team_id,))
                conn.commit()
            finally:
                conn.close()
        if row:
            row_vals = dict(row)
            set_undo(f"removing {row_vals['name']}", lambda: _revert_delete_team(row_vals))
        self._send_json({"ok": True})

    def _api_adjust_score(self, team_id, body):
        delta = body.get("delta", 0)
        with DB_LOCK:
            conn = get_db()
            try:
                row = conn.execute("SELECT * FROM teams WHERE id=?", (team_id,)).fetchone()
                if not row:
                    return self._send_error_json("Team not found", 404)
                previous_score = row["score"]
                team_name = row["name"]
                conn.execute(
                    "UPDATE teams SET score = score + ? WHERE id=?", (int(delta), team_id)
                )
                conn.commit()
                row = conn.execute("SELECT * FROM teams WHERE id=?", (team_id,)).fetchone()
            finally:
                conn.close()
        set_undo(f"score change for {team_name}", lambda: _revert_team_state(team_id, team_name, previous_score))
        self._send_json({"team": team_to_json(row)})

    # ---- resets -------------------------------------------------------
    def _api_reset_scores(self):
        with DB_LOCK:
            conn = get_db()
            try:
                conn.execute("UPDATE teams SET score=0")
                conn.commit()
            finally:
                conn.close()
        self._send_json({"ok": True})

    def _api_reset_teams(self):
        with DB_LOCK:
            conn = get_db()
            try:
                previous_teams = [
                    dict(r)
                    for r in conn.execute("SELECT * FROM teams ORDER BY position, id").fetchall()
                ]
                conn.execute("DELETE FROM teams")
                conn.execute("INSERT INTO teams (name, score, position) VALUES ('Team 1', 0, 0)")
                conn.execute("INSERT INTO teams (name, score, position) VALUES ('Team 2', 0, 1)")
                conn.commit()
            finally:
                conn.close()
        set_undo("resetting teams", lambda: _revert_teams_snapshot(previous_teams))
        self._send_json({"ok": True})

    def _api_reset_board(self):
        with DB_LOCK:
            conn = get_db()
            try:
                conn.execute("UPDATE questions SET used=0")
                conn.commit()
            finally:
                conn.close()
        self._send_json({"ok": True})

    def _api_reset_full(self):
        with DB_LOCK:
            conn = get_db()
            try:
                conn.execute("UPDATE questions SET used=0")
                conn.execute("UPDATE teams SET score=0")
                set_meta(conn, "current_round", "1")
                conn.commit()
            finally:
                conn.close()
        self._send_json({"ok": True})

    def _api_exit(self):
        self._send_json({"ok": True})
        # Respond first, then shut down from a separate thread shortly after
        # (server.shutdown() must not be called from the thread running
        # serve_forever(), and would otherwise block this response from
        # ever being flushed to the client).
        threading.Timer(0.3, self.server.shutdown).start()

    # ---- admin: categories -------------------------------------------
    def _api_admin_get_categories(self, qs):
        round_num = qs.get("round", [None])[0]
        with DB_LOCK:
            conn = get_db()
            try:
                if round_num is not None:
                    cats = conn.execute(
                        "SELECT * FROM categories WHERE round=? ORDER BY position, id",
                        (int(round_num),),
                    ).fetchall()
                else:
                    cats = conn.execute(
                        "SELECT * FROM categories ORDER BY round, position, id"
                    ).fetchall()
                result = []
                for cat in cats:
                    qrows = conn.execute(
                        "SELECT * FROM questions WHERE category_id=? ORDER BY position, value",
                        (cat["id"],),
                    ).fetchall()
                    d = row_to_dict(cat)
                    d["questions"] = [row_to_dict(q) for q in qrows]
                    result.append(d)
            finally:
                conn.close()
        self._send_json({"categories": result})

    def _api_admin_add_category(self, body):
        name = (body.get("name") or "").strip() or "New Category"
        round_num = int(body.get("round", 1))
        with DB_LOCK:
            conn = get_db()
            try:
                pos_row = conn.execute(
                    "SELECT COALESCE(MAX(position), -1) AS m FROM categories WHERE round=?",
                    (round_num,),
                ).fetchone()
                pos = pos_row["m"] + 1
                cur = conn.execute(
                    "INSERT INTO categories (round, name, position) VALUES (?, ?, ?)",
                    (round_num, name, pos),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM categories WHERE id=?", (cur.lastrowid,)).fetchone()
            finally:
                conn.close()
        self._send_json({"category": row_to_dict(row)})

    def _api_admin_update_category(self, cat_id, body):
        fields, values = [], []
        for key in ("name", "round", "position"):
            if key in body:
                fields.append(f"{key}=?")
                values.append(body[key])
        if not fields:
            return self._send_error_json("Nothing to update")
        values.append(cat_id)
        with DB_LOCK:
            conn = get_db()
            try:
                conn.execute(f"UPDATE categories SET {', '.join(fields)} WHERE id=?", values)
                conn.commit()
                row = conn.execute("SELECT * FROM categories WHERE id=?", (cat_id,)).fetchone()
                if not row:
                    return self._send_error_json("Category not found", 404)
            finally:
                conn.close()
        self._send_json({"category": row_to_dict(row)})

    def _api_admin_delete_category(self, cat_id):
        with DB_LOCK:
            conn = get_db()
            try:
                conn.execute("DELETE FROM categories WHERE id=?", (cat_id,))
                conn.commit()
            finally:
                conn.close()
        self._send_json({"ok": True})

    # ---- admin: questions -------------------------------------------
    def _api_admin_add_question(self, body):
        category_id = body.get("category_id")
        if not category_id:
            return self._send_error_json("category_id is required")
        value = int(body.get("value", 100))
        question_text = body.get("question_text", "")
        answer_text = body.get("answer_text", "")
        is_daily_double = 1 if body.get("is_daily_double") else 0
        with DB_LOCK:
            conn = get_db()
            try:
                pos_row = conn.execute(
                    "SELECT COALESCE(MAX(position), -1) AS m FROM questions WHERE category_id=?",
                    (category_id,),
                ).fetchone()
                pos = pos_row["m"] + 1
                cur = conn.execute(
                    """INSERT INTO questions
                       (category_id, value, position, question_text, answer_text, is_daily_double, used)
                       VALUES (?, ?, ?, ?, ?, ?, 0)""",
                    (category_id, value, pos, question_text, answer_text, is_daily_double),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM questions WHERE id=?", (cur.lastrowid,)).fetchone()
            finally:
                conn.close()
        self._send_json({"question": row_to_dict(row)})

    def _api_admin_update_question(self, qid, body):
        fields, values = [], []
        allowed = ("category_id", "value", "position", "question_text",
                   "answer_text", "is_daily_double", "used")
        for key in allowed:
            if key in body:
                fields.append(f"{key}=?")
                v = body[key]
                if key == "is_daily_double" or key == "used":
                    v = 1 if v else 0
                values.append(v)
        if not fields:
            return self._send_error_json("Nothing to update")
        values.append(qid)
        with DB_LOCK:
            conn = get_db()
            try:
                conn.execute(f"UPDATE questions SET {', '.join(fields)} WHERE id=?", values)
                conn.commit()
                row = conn.execute("SELECT * FROM questions WHERE id=?", (qid,)).fetchone()
                if not row:
                    return self._send_error_json("Question not found", 404)
            finally:
                conn.close()
        self._send_json({"question": row_to_dict(row)})

    def _api_admin_delete_question(self, qid):
        with DB_LOCK:
            conn = get_db()
            try:
                conn.execute("DELETE FROM questions WHERE id=?", (qid,))
                conn.commit()
            finally:
                conn.close()
        self._send_json({"ok": True})


def clear_latex_cache():
    for entry in CACHE_DIR.iterdir():
        try:
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
        except OSError:
            pass


def main():
    global _active_db_name
    _migrate_legacy_db()
    _active_db_name = _load_initial_active_name()
    ensure_active_db()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Jeopardy server running at http://{HOST}:{PORT}/")
    print(f"  Game board:      http://localhost:{PORT}/")
    print(f"  Question editor: http://localhost:{PORT}/editor")
    print(f"  Database dir:    {DB_DIR}")
    print(f"  Active database: {get_active_db_name()}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()
    else:
        print("\nShutting down (exit requested from the game interface).")
    finally:
        clear_latex_cache()
        print(f"Cleared {CACHE_DIR}")


if __name__ == "__main__":
    main()
