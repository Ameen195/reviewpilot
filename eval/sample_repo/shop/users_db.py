import sqlite3


def connect(path=":memory:"):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)")
    return conn


def add_user(conn, name, email):
    cur = conn.execute("INSERT INTO users (name, email) VALUES (?, ?)", (name, email))
    conn.commit()
    return cur.lastrowid


def get_user(conn, user_id):
    row = conn.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        return None
    return {"id": row[0], "name": row[1], "email": row[2]}


def find_by_email(conn, email):
    rows = conn.execute("SELECT id, name FROM users WHERE email = ?", (email,)).fetchall()
    return [{"id": r[0], "name": r[1]} for r in rows]


def delete_user(conn, user_id):
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()


def count_users(conn):
    return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
