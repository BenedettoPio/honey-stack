"""Honey-Stack - Database (SQLite).

Conserva gli honeytoken attivi e lo storico degli allarmi.
Uso da terminale:
    python -m honeystack.db init
    python -m honeystack.db add USER_ID NOME PROJECT_ID [LUOGO]
    python -m honeystack.db list
    python -m honeystack.db alerts
"""
import os
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone

DB_PATH = os.environ.get(
    "HONEYSTACK_DB", "/opt/stack/data/honey-stack/honeystack.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS honeytokens (
    user_id    TEXT PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    project_id TEXT NOT NULL,
    luogo      TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    active     INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id    TEXT UNIQUE,
    user_id     TEXT NOT NULL,
    name        TEXT NOT NULL,
    outcome     TEXT NOT NULL,
    source_ip   TEXT,
    agent       TEXT,
    event_time  TEXT NOT NULL,
    received_at TEXT NOT NULL
);
"""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path=DB_PATH):
    """Apre il database e crea le tabelle se non esistono."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def add_honeytoken(user_id, name, project_id, luogo="", path=DB_PATH):
    with closing(connect(path)) as conn, conn:
        conn.execute(
            "INSERT OR REPLACE INTO honeytokens "
            "(user_id, name, project_id, luogo, created_at, active) "
            "VALUES (?, ?, ?, ?, ?, 1)",
            (user_id, name, project_id, luogo, _now()))


def disable_honeytoken(user_id, path=DB_PATH):
    with closing(connect(path)) as conn, conn:
        conn.execute("UPDATE honeytokens SET active = 0 WHERE user_id = ?",
                     (user_id,))


def get_active_honeytoken(user_id, path=DB_PATH):
    """Restituisce l'honeytoken attivo con quell'ID utente, o None."""
    with closing(connect(path)) as conn:
        return conn.execute(
            "SELECT * FROM honeytokens WHERE user_id = ? AND active = 1",
            (user_id,)).fetchone()


def list_honeytokens(only_active=True, path=DB_PATH):
    query = "SELECT * FROM honeytokens"
    if only_active:
        query += " WHERE active = 1"
    with closing(connect(path)) as conn:
        return conn.execute(query + " ORDER BY created_at").fetchall()


def save_alert(event_id, user_id, name, outcome, source_ip, agent,
               event_time, path=DB_PATH):
    """Salva un allarme; restituisce False se era gia' stato salvato."""
    with closing(connect(path)) as conn, conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO alerts "
            "(event_id, user_id, name, outcome, source_ip, agent, "
            "event_time, received_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (event_id, user_id, name, outcome, source_ip, agent,
             event_time, _now()))
        return cur.rowcount == 1


def list_alerts(limit=50, path=DB_PATH):
    with closing(connect(path)) as conn:
        return conn.execute(
            "SELECT * FROM alerts ORDER BY id DESC LIMIT ?",
            (limit,)).fetchall()


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    cmd = argv[1]
    if cmd == "init":
        connect().close()
        print("Database pronto:", DB_PATH)
    elif cmd == "add" and len(argv) >= 5:
        luogo = argv[5] if len(argv) > 5 else ""
        add_honeytoken(argv[2], argv[3], argv[4], luogo)
        print("Honeytoken registrato:", argv[3])
    elif cmd == "list":
        for h in list_honeytokens():
            print(h["name"], h["user_id"], h["luogo"], h["created_at"])
    elif cmd == "alerts":
        for a in list_alerts():
            print(a["id"], a["event_time"], a["name"], a["outcome"],
                  a["source_ip"], a["agent"])
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
