#!/usr/bin/env python3
"""
Initializes the SQLite database for the Jeopardy game.
Safe to run multiple times: it will only create tables that don't exist,
and will only seed sample data if the database is completely empty.

Usage:
    python3 init_db.py            # create tables, seed sample data if empty
    python3 init_db.py --wipe     # DROP all tables and recreate + reseed
"""
import os
import sys
from pathlib import Path

from sqlite_helper import (
    build_schema,
    connect,
    insert_default_teams,
    is_empty,
    set_meta,
    wipe,
)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = os.environ.get("JEOPARDY_DB", str(BASE_DIR / "jeopardy.db"))

# Sample seed data for Round 1 (Jeopardy) and Round 2 (Double Jeopardy).
# Each category is a tuple of (category_name, questions), where each
# question is a tuple of (value, question_text, answer_text, is_daily_double).
# question_text/answer_text may contain LaTeX math delimited by $...$, which
# the server renders to an image at display time (see server.py's
# render_latex_png). is_daily_double is 1 for exactly one question per round
# by convention, 0 otherwise.
SAMPLE_CATEGORIES_R1 = [
    ("Algebra", [
        (100, r"Solve for $x$: $2x + 4 = 10$", r"$x = 3$", 0),
        (200, r"Simplify: $(x+2)^2$", r"$x^2 + 4x + 4$", 0),
        (300, r"What is the slope of the line $y = 3x - 7$?", r"$3$", 0),
        (400, r"Factor: $x^2 - 9$", r"$(x-3)(x+3)$", 0),
        (500, r"Solve the system: $x + y = 5$, $x - y = 1$", r"$x=3, y=2$", 1),
    ]),
    ("Chemistry", [
        (100, r"What is the chemical symbol for Gold?", r"Au", 0),
        (200, r"Balance: $H_2 + O_2 \rightarrow H_2O$", r"$2H_2 + O_2 \rightarrow 2H_2O$", 0),
        (300, r"What is the pH of a neutral solution at $25^\circ C$?", r"$7$", 0),
        (400, r"What is Avogadro's number, approximately?", r"$6.022 \times 10^{23}$", 0),
        (500, r"What is the atomic number of Carbon?", r"$6$", 0),
    ]),
    ("World History", [
        (100, r"In what year did World War II end?", r"1945", 0),
        (200, r"Who was the first President of the United States?", r"George Washington", 0),
        (300, r"Which empire built the Colosseum?", r"The Roman Empire", 0),
        (400, r"What wall fell in 1989?", r"The Berlin Wall", 0),
        (500, r"Which treaty ended World War I?", r"The Treaty of Versailles", 0),
    ]),
    ("Physics", [
        (100, r"What is the unit of force?", r"The Newton (N)", 0),
        (200, r"State Newton's Second Law as a formula.", r"$F = ma$", 0),
        (300, r"What is the speed of light in a vacuum, approximately?", r"$3 \times 10^8\ m/s$", 0),
        (400, r"What is the formula for kinetic energy?", r"$KE = \frac{1}{2}mv^2$", 0),
        (500, r"What force keeps planets in orbit around the sun?", r"Gravity", 0),
    ]),
    ("Potpourri", [
        (100, r"How many continents are there?", r"7", 0),
        (200, r"What is the largest planet in our solar system?", r"Jupiter", 0),
        (300, r"What is the capital of France?", r"Paris", 0),
        (400, r"What gas do plants absorb from the atmosphere?", r"Carbon dioxide ($CO_2$)", 0),
        (500, r"What is the longest river in the world?", r"The Nile", 0),
    ]),
]

SAMPLE_CATEGORIES_R2 = [
    ("Geometry", [
        (200, r"What is the area of a circle with radius $r$?", r"$A = \pi r^2$", 0),
        (400, r"How many degrees are in the interior angles of a triangle?", r"$180^\circ$", 0),
        (600, r"What is the Pythagorean theorem?", r"$a^2 + b^2 = c^2$", 0),
        (800, r"What is the volume of a sphere with radius $r$?", r"$V = \frac{4}{3}\pi r^3$", 1),
        (1000, r"What is the sum of interior angles of a hexagon?", r"$720^\circ$", 0),
    ]),
    ("Biology", [
        (200, r"What is the powerhouse of the cell?", r"The mitochondria", 0),
        (400, r"What molecule carries genetic information?", r"DNA", 0),
        (600, r"What process do plants use to make food from sunlight?", r"Photosynthesis", 0),
        (800, r"What are the four nitrogenous bases in DNA?", r"Adenine, Thymine, Guanine, Cytosine", 0),
        (1000, r"What is the process of cell division called?", r"Mitosis", 0),
    ]),
    ("Literature", [
        (200, r"Who wrote 'Romeo and Juliet'?", r"William Shakespeare", 0),
        (400, r"What novel begins with 'Call me Ishmael'?", r"Moby-Dick", 0),
        (600, r"Who wrote '1984'?", r"George Orwell", 0),
        (800, r"What is the term for a story that runs parallel to the main plot?", r"A subplot", 0),
        (1000, r"Who wrote 'One Hundred Years of Solitude'?", r"Gabriel García Márquez", 0),
    ]),
    ("Calculus", [
        (200, r"What is the derivative of $x^2$?", r"$2x$", 0),
        (400, r"What is $\int x\, dx$?", r"$\frac{x^2}{2} + C$", 0),
        (600, r"What is the derivative of $\sin(x)$?", r"$\cos(x)$", 0),
        (800, r"What does $\lim_{x \to 0} \frac{\sin x}{x}$ equal?", r"$1$", 0),
        (1000, r"What is the derivative of $e^x$?", r"$e^x$", 0),
    ]),
    ("Geography", [
        (200, r"What is the smallest country in the world?", r"Vatican City", 0),
        (400, r"What mountain range separates Europe and Asia?", r"The Ural Mountains", 0),
        (600, r"What is the driest desert in the world?", r"The Atacama Desert", 0),
        (800, r"Which country has the most time zones?", r"France (12)", 0),
        (1000, r"What is the deepest point in the ocean?", r"The Mariana Trench (Challenger Deep)", 0),
    ]),
]

# The single Final Jeopardy category/question, as (category_name,
# question_text, answer_text). Final Jeopardy has no point value or
# daily-double flag since the wager is entered live during play.
SAMPLE_FINAL = ("Astronomy", r"This dwarf planet, discovered in 1930, was reclassified in 2006.",
                r"What is Pluto?")


def seed(conn):
    """Populate an empty database with the sample categories, questions, Final
    Jeopardy clue, two default teams, and current_round=1."""
    for round_num, cat_set in ((1, SAMPLE_CATEGORIES_R1), (2, SAMPLE_CATEGORIES_R2)):
        for pos, (cat_name, questions) in enumerate(cat_set):
            cur = conn.execute(
                "INSERT INTO categories (round, name, position) VALUES (?, ?, ?)",
                (round_num, cat_name, pos),
            )
            cat_id = cur.lastrowid
            for qpos, (value, qtext, atext, dd) in enumerate(questions):
                conn.execute(
                    """INSERT INTO questions
                       (category_id, value, position, question_text, answer_text, is_daily_double, used)
                       VALUES (?, ?, ?, ?, ?, ?, 0)""",
                    (cat_id, value, qpos, qtext, atext, dd),
                )
    # Final Jeopardy
    fname, fq, fa = SAMPLE_FINAL
    cur = conn.execute(
        "INSERT INTO categories (round, name, position) VALUES (3, ?, 0)", (fname,)
    )
    cat_id = cur.lastrowid
    conn.execute(
        """INSERT INTO questions
           (category_id, value, position, question_text, answer_text, is_daily_double, used)
           VALUES (?, 0, 0, ?, ?, 0, 0)""",
        (cat_id, fq, fa),
    )

    insert_default_teams(conn)
    set_meta(conn, "current_round", "1")
    conn.commit()


def main():
    """CLI entry point: build/refresh the schema, seeding sample data on an
    empty database or, with --wipe, unconditionally."""
    wipe_flag = "--wipe" in sys.argv
    conn = connect(DB_PATH)
    if wipe_flag:
        print(f"Wiping database at {DB_PATH} ...")
        wipe(conn)
    build_schema(conn)
    if wipe_flag or is_empty(conn):
        print("Seeding sample data ...")
        seed(conn)
    else:
        print("Database already has data; leaving it as-is (use --wipe to reset).")
    conn.close()
    print(f"Database ready at {DB_PATH}")


if __name__ == "__main__":
    main()
