"""
ToDo2 - a catchy to-do list app (Flask + SQLite).

Main screen shows all pending work, with a search bar. Ticking a
task removes it from the main screen and it appears in History.
A 3-dots menu opens History (completed tasks only) and Due Tasks
(all pending work, overdue included, with a count badge).
History and Due pages have a search bar (search by task name) and a
date picker (pick a date). Tasks can be edited.
Add-task form auto-fills today's date + current time (still editable).
Clear completed asks for confirmation. Dark / light theme, remembered
in the browser. No categories, by the owner's choice. No login -
opens straight to your tasks.
"""

import os
import sqlite3
from datetime import date, datetime

from flask import Flask, g, redirect, render_template, request, url_for

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

DATABASE = os.path.join(app.instance_path, "todo.db")

# Permanent Neon Postgres when DATABASE_URL is set (on Render),
# local SQLite otherwise (on the laptop).
DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_PG = DATABASE_URL.startswith("postgres")


class _PGConnection:
    """Thin wrapper so the rest of the app can use sqlite-style calls."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        cur = self._conn.cursor()
        cur.execute(sql.replace("?", "%s").replace(" LIKE ", " ILIKE "), params)
        return cur

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


# ---------- database ----------


def get_db():
    if "db" not in g:
        if USE_PG:
            import psycopg2
            import psycopg2.extras

            raw = psycopg2.connect(
                DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor
            )
            g.db = _PGConnection(raw)
        else:
            os.makedirs(app.instance_path, exist_ok=True)
            conn = sqlite3.connect(DATABASE)
            conn.row_factory = sqlite3.Row
            g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    pk = "SERIAL PRIMARY KEY" if USE_PG else "INTEGER PRIMARY KEY AUTOINCREMENT"
    db.execute(f"""
        CREATE TABLE IF NOT EXISTS tasks (
            id {pk},
            title TEXT NOT NULL,
            due_date TEXT NOT NULL DEFAULT '',
            due_time TEXT NOT NULL DEFAULT '',
            done INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT ''
        )
        """)
    db.commit()


def due_count(db):
    # Count matches the Due page: all pending tasks, overdue included.
    # Aliased as c so both SQLite rows and Postgres dict rows work.
    return db.execute("SELECT COUNT(*) AS c FROM tasks WHERE done = 0").fetchone()["c"]


# ---------- pages ----------


@app.route("/")
def index():
    db = get_db()
    q = request.args.get("q", "").strip()
    d = request.args.get("d", "").strip()
    today = date.today().isoformat()
    # Main screen shows all pending work; ticked tasks live in History.
    # The search bar filters by name, the date picker by due date.
    sql = "SELECT * FROM tasks WHERE done = 0"
    params = []
    if q:
        sql += " AND title LIKE ?"
        params.append("%" + q + "%")
    if d:
        sql += " AND due_date = ?"
        params.append(d)
    sql += """ ORDER BY CASE WHEN due_date = '' THEN 1 ELSE 0 END,
        due_date, due_time, id DESC"""
    tasks = db.execute(sql, params).fetchall()
    total = db.execute("SELECT COUNT(*) AS c FROM tasks").fetchone()["c"]
    done_count = db.execute(
        "SELECT COUNT(*) AS c FROM tasks WHERE done = 1"
    ).fetchone()["c"]
    percent = round(done_count * 100 / total) if total else 0
    return render_template(
        "index.html",
        tasks=tasks,
        total=total,
        done_count=done_count,
        due_count=due_count(db),
        percent=percent,
        today=today,
        q=q,
        d=d,
    )


@app.route("/history")
def history():
    db = get_db()
    q = request.args.get("q", "").strip()
    d = request.args.get("d", "").strip()
    today = date.today().isoformat()
    # History shows completed tasks only.
    # The date filter uses the task's due date, so any date can be checked.
    sql = "SELECT * FROM tasks WHERE done = 1"
    params = []
    if q:
        sql += " AND title LIKE ?"
        params.append("%" + q + "%")
    if d:
        sql += " AND due_date = ?"
        params.append(d)
    sql += " ORDER BY created_at DESC, id DESC"
    tasks = db.execute(sql, params).fetchall()
    return render_template(
        "history.html", tasks=tasks, q=q, d=d, due_count=due_count(db)
    )


@app.route("/due")
def due():
    db = get_db()
    q = request.args.get("q", "").strip()
    d = request.args.get("d", "").strip()
    today = date.today().isoformat()
    # Due shows all pending work, overdue included.
    # Picking a date narrows it to tasks due that day.
    if d:
        sql = "SELECT * FROM tasks WHERE done = 0 AND due_date = ?"
        params = [d]
    else:
        sql = "SELECT * FROM tasks WHERE done = 0"
        params = []
    if q:
        sql += " AND title LIKE ?"
        params.append("%" + q + "%")
    sql += """ ORDER BY CASE WHEN due_date = '' THEN 1 ELSE 0 END,
        due_date, due_time, id DESC"""
    tasks = db.execute(sql, params).fetchall()
    return render_template(
        "due.html",
        tasks=tasks,
        q=q,
        d=d,
        today=today,
        due_count=due_count(db),
    )


@app.route("/edit/<int:task_id>", methods=["GET", "POST"])
def edit_task(task_id):
    db = get_db()
    task = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not task:
        return redirect(url_for("index"))
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        due_date = request.form.get("due_date", "").strip()
        due_time = request.form.get("due_time", "").strip()
        if title:
            db.execute(
                "UPDATE tasks SET title = ?, due_date = ?, due_time = ? WHERE id = ?",
                (title, due_date, due_time, task_id),
            )
            db.commit()
        return redirect(request.form.get("next", "") or url_for("index"))
    return render_template(
        "edit.html",
        t=task,
        back=request.referrer or url_for("index"),
        due_count=due_count(db),
    )


# ---------- actions ----------


@app.route("/add", methods=["POST"])
def add_task():
    title = request.form.get("title", "").strip()
    due_date = request.form.get("due_date", "").strip()
    due_time = request.form.get("due_time", "").strip()
    if title:
        db = get_db()
        db.execute(
            "INSERT INTO tasks (title, due_date, due_time, created_at) VALUES (?, ?, ?, ?)",
            (title, due_date, due_time, datetime.now().strftime("%Y-%m-%d %H:%M")),
        )
        db.commit()
    return redirect(url_for("index"))


@app.route("/toggle/<int:task_id>", methods=["POST"])
def toggle_task(task_id):
    db = get_db()
    task = db.execute("SELECT done FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if task:
        db.execute(
            "UPDATE tasks SET done = ? WHERE id = ?", (1 - task["done"], task_id)
        )
        db.commit()
    return redirect(request.referrer or url_for("index"))


@app.route("/delete/<int:task_id>", methods=["POST"])
def delete_task(task_id):
    db = get_db()
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()
    return redirect(request.referrer or url_for("index"))


@app.route("/clear-completed", methods=["POST"])
def clear_completed():
    db = get_db()
    db.execute("DELETE FROM tasks WHERE done = 1")
    db.commit()
    return redirect(url_for("index"))


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(debug=True)
