"""
ToDo2 - a catchy to-do list app (Flask + SQLite).

Main screen shows all pending work, with a search bar. Ticking a
task removes it from the main screen and it appears in History.
A 3-dots menu opens History (completed tasks only) and Due Tasks
(all pending work, overdue included, with a count badge).
History and Due pages have a search bar (search by
task name) and a date picker (pick a date). Tasks can be edited.
Add-task form auto-fills today's date + current time (still editable).
Clear completed asks for confirmation. Dark / light theme, remembered
in the browser. No categories, by the owner's choice.

Login: every page needs an account (name, username, password).
Passwords are hashed, never stored in plain text. Login always
lasts 30 days, so it won't ask you to login again and again.
"""

import os
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps

from flask import Flask, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.permanent_session_lifetime = timedelta(days=30)

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

    def rollback(self):
        self._conn.rollback()

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
        CREATE TABLE IF NOT EXISTS users (
            id {pk},
            name TEXT NOT NULL,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL
        )
        """)
    db.execute(f"""
        CREATE TABLE IF NOT EXISTS tasks (
            id {pk},
            title TEXT NOT NULL,
            due_date TEXT NOT NULL DEFAULT '',
            due_time TEXT NOT NULL DEFAULT '',
            done INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT '',
            user_id INTEGER NOT NULL DEFAULT 0
        )
        """)
    db.commit()
    # Migration for databases made before login existed: add user_id
    # to the old tasks table. (Fresh tables already have it above.)
    try:
        db.execute("ALTER TABLE tasks ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0")
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


def due_count(db, user_id):
    # Count matches the Due page: all pending tasks, overdue included.
    # Aliased as c so both SQLite rows and Postgres dict rows work.
    return db.execute(
        "SELECT COUNT(*) AS c FROM tasks WHERE done = 0 AND user_id = ?",
        (user_id,),
    ).fetchone()["c"]


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


# ---------- auth ----------


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("index"))
    error = ""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        if not name or not username or not password:
            error = "Please fill in all fields."
        elif password != confirm:
            error = "Passwords do not match."
        else:
            db = get_db()
            existing = db.execute(
                "SELECT id FROM users WHERE username = ?", (username,)
            ).fetchone()
            if existing:
                error = "That username is already taken. Pick another one."
            else:
                if USE_PG:
                    cur = db.execute(
                        "INSERT INTO users (name, username, password_hash) "
                        "VALUES (?, ?, ?) RETURNING id",
                        (name, username, generate_password_hash(password)),
                    )
                    new_id = cur.fetchone()["id"]
                else:
                    cur = db.execute(
                        "INSERT INTO users (name, username, password_hash) "
                        "VALUES (?, ?, ?)",
                        (name, username, generate_password_hash(password)),
                    )
                    new_id = cur.lastrowid
                # First account adopts tasks made before login existed.
                count = db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
                if count == 1:
                    db.execute(
                        "UPDATE tasks SET user_id = ? WHERE user_id = 0",
                        (new_id,),
                    )
                db.commit()
                session["user_id"] = new_id
                session["username"] = username
                session.permanent = True
                return redirect(url_for("index"))
    return render_template("register.html", error=error)


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("index"))
    error = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            # Always remembered: login lasts 30 days, no checkbox needed.
            session.permanent = True
            nxt = request.form.get("next", "") or url_for("index")
            if not nxt.startswith("/") or nxt.startswith("//"):
                nxt = url_for("index")
            return redirect(nxt)
        error = "Wrong username or password."
    return render_template("login.html", error=error, next=request.args.get("next", ""))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- pages ----------


@app.route("/sw.js")
def service_worker():
    """Serve the service worker from the root so it can control the whole app."""
    return app.send_static_file("sw.js")


@app.route("/")
@login_required
def index():
    db = get_db()
    uid = session["user_id"]
    q = request.args.get("q", "").strip()
    d = request.args.get("d", "").strip()
    today = date.today().isoformat()
    # Main screen shows all pending work; ticked tasks live in History.
    # The search bar filters by name, the date picker by due date.
    sql = "SELECT * FROM tasks WHERE done = 0 AND user_id = ?"
    params = [uid]
    if q:
        sql += " AND title LIKE ?"
        params.append("%" + q + "%")
    if d:
        sql += " AND due_date = ?"
        params.append(d)
    sql += """ ORDER BY CASE WHEN due_date = '' THEN 1 ELSE 0 END,
        due_date, due_time, id DESC"""
    tasks = db.execute(sql, params).fetchall()
    total = db.execute(
        "SELECT COUNT(*) AS c FROM tasks WHERE user_id = ?", (uid,)
    ).fetchone()["c"]
    done_count = db.execute(
        "SELECT COUNT(*) AS c FROM tasks WHERE done = 1 AND user_id = ?",
        (uid,),
    ).fetchone()["c"]
    percent = round(done_count * 100 / total) if total else 0
    return render_template(
        "index.html",
        tasks=tasks,
        total=total,
        done_count=done_count,
        due_count=due_count(db, uid),
        percent=percent,
        today=today,
        q=q,
        d=d,
        username=session.get("username"),
    )


@app.route("/history")
@login_required
def history():
    db = get_db()
    uid = session["user_id"]
    q = request.args.get("q", "").strip()
    d = request.args.get("d", "").strip()
    today = date.today().isoformat()
    # History shows completed tasks only.
    # The date filter uses the task's due date, so any date can be checked.
    sql = "SELECT * FROM tasks WHERE done = 1 AND user_id = ?"
    params = [uid]
    if q:
        sql += " AND title LIKE ?"
        params.append("%" + q + "%")
    if d:
        sql += " AND due_date = ?"
        params.append(d)
    sql += " ORDER BY created_at DESC, id DESC"
    tasks = db.execute(sql, params).fetchall()
    return render_template(
        "history.html",
        tasks=tasks,
        q=q,
        d=d,
        due_count=due_count(db, uid),
        username=session.get("username"),
    )


@app.route("/due")
@login_required
def due():
    db = get_db()
    uid = session["user_id"]
    q = request.args.get("q", "").strip()
    d = request.args.get("d", "").strip()
    today = date.today().isoformat()
    # Due shows all pending work, overdue included.
    # Picking a date narrows it to tasks due that day.
    sql = "SELECT * FROM tasks WHERE done = 0 AND user_id = ?"
    params = [uid]
    if d:
        sql += " AND due_date = ?"
        params.append(d)
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
        due_count=due_count(db, uid),
        username=session.get("username"),
    )


@app.route("/edit/<int:task_id>", methods=["GET", "POST"])
@login_required
def edit_task(task_id):
    db = get_db()
    uid = session["user_id"]
    task = db.execute(
        "SELECT * FROM tasks WHERE id = ? AND user_id = ?", (task_id, uid)
    ).fetchone()
    if not task:
        return redirect(url_for("index"))
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        due_date = request.form.get("due_date", "").strip()
        due_time = request.form.get("due_time", "").strip()
        if title:
            db.execute(
                "UPDATE tasks SET title = ?, due_date = ?, due_time = ? "
                "WHERE id = ? AND user_id = ?",
                (title, due_date, due_time, task_id, uid),
            )
            db.commit()
        return redirect(request.form.get("next", "") or url_for("index"))
    return render_template(
        "edit.html",
        t=task,
        back=request.referrer or url_for("index"),
        due_count=due_count(db, uid),
        username=session.get("username"),
    )


# ---------- actions ----------


@app.route("/add", methods=["POST"])
@login_required
def add_task():
    title = request.form.get("title", "").strip()
    due_date = request.form.get("due_date", "").strip()
    due_time = request.form.get("due_time", "").strip()
    if title:
        db = get_db()
        db.execute(
            "INSERT INTO tasks (title, due_date, due_time, created_at, user_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                title,
                due_date,
                due_time,
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                session["user_id"],
            ),
        )
        db.commit()
    return redirect(url_for("index"))


@app.route("/toggle/<int:task_id>", methods=["POST"])
@login_required
def toggle_task(task_id):
    db = get_db()
    uid = session["user_id"]
    task = db.execute(
        "SELECT done FROM tasks WHERE id = ? AND user_id = ?", (task_id, uid)
    ).fetchone()
    if task:
        db.execute(
            "UPDATE tasks SET done = ? WHERE id = ? AND user_id = ?",
            (1 - task["done"], task_id, uid),
        )
        db.commit()
    return redirect(request.referrer or url_for("index"))


@app.route("/delete/<int:task_id>", methods=["POST"])
@login_required
def delete_task(task_id):
    db = get_db()
    uid = session["user_id"]
    db.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, uid))
    db.commit()
    return redirect(request.referrer or url_for("index"))


@app.route("/clear-completed", methods=["POST"])
@login_required
def clear_completed():
    db = get_db()
    db.execute(
        "DELETE FROM tasks WHERE done = 1 AND user_id = ?",
        (session["user_id"],),
    )
    db.commit()
    return redirect(url_for("index"))


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(debug=True)
