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

from honeystack import config

DB_PATH = config.get("db_path")

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
CREATE TABLE IF NOT EXISTS quarantine (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    port_id         TEXT NOT NULL,
    server_id       TEXT,
    server_name     TEXT,
    source_ip       TEXT,
    honeytoken      TEXT,
    original_groups TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    released_at     TEXT
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


def alerts_from_ip_since(source_ip, since, path=DB_PATH):
    """Allarmi da un IP ricevuti a partire da since (ISO, UTC)."""
    with closing(connect(path)) as conn:
        return conn.execute(
            "SELECT * FROM alerts WHERE source_ip = ? AND received_at >= ? "
            "ORDER BY id", (source_ip, since)).fetchall()


def add_quarantine(port_id, server_id, server_name, source_ip, honeytoken,
                   original_groups, path=DB_PATH):
    """Registra una VM in quarantena; restituisce l'id della voce."""
    with closing(connect(path)) as conn, conn:
        cur = conn.execute(
            "INSERT INTO quarantine (port_id, server_id, server_name, "
            "source_ip, honeytoken, original_groups, started_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (port_id, server_id, server_name, source_ip, honeytoken,
             original_groups, _now()))
        return cur.lastrowid


def delete_quarantine(voce_id, path=DB_PATH):
    with closing(connect(path)) as conn, conn:
        conn.execute("DELETE FROM quarantine WHERE id = ?", (voce_id,))


def release_quarantine(voce_id, path=DB_PATH):
    with closing(connect(path)) as conn, conn:
        conn.execute("UPDATE quarantine SET released_at = ? WHERE id = ?",
                     (_now(), voce_id))


def active_quarantine_for_port(port_id, path=DB_PATH):
    with closing(connect(path)) as conn:
        return conn.execute(
            "SELECT * FROM quarantine WHERE port_id = ? AND "
            "released_at IS NULL", (port_id,)).fetchone()


def active_quarantine_for(vm_o_ip, path=DB_PATH):
    """Quarantena attiva per nome della VM, IP o id della voce."""
    with closing(connect(path)) as conn:
        return conn.execute(
            "SELECT * FROM quarantine WHERE released_at IS NULL AND "
            "(server_name = ? OR source_ip = ? OR CAST(id AS TEXT) = ?) "
            "ORDER BY id DESC", (vm_o_ip, vm_o_ip, str(vm_o_ip))
        ).fetchone()


def list_quarantine(only_active=True, path=DB_PATH):
    query = "SELECT * FROM quarantine"
    if only_active:
        query += " WHERE released_at IS NULL"
    with closing(connect(path)) as conn:
        return conn.execute(query + " ORDER BY id DESC").fetchall()


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
