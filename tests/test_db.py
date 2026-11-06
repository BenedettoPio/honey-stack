"""Test del database (db.py)."""
from honeystack import db


def test_honeytoken_registrato_e_attivo():
    db.add_honeytoken("u1", "backup_admin", "p1", "repository interno")
    esca = db.get_active_honeytoken("u1")
    assert esca["name"] == "backup_admin"
    assert esca["luogo"] == "repository interno"
    assert esca["active"] == 1


def test_utente_sconosciuto_non_e_un_honeytoken():
    assert db.get_active_honeytoken("nessuno") is None


def test_honeytoken_disattivato():
    db.add_honeytoken("u1", "backup_admin", "p1")
    db.disable_honeytoken("u1")
    assert db.get_active_honeytoken("u1") is None
    assert db.list_honeytokens() == []
    # resta nello storico, per i vecchi allarmi
    assert len(db.list_honeytokens(only_active=False)) == 1


def test_allarme_salvato_una_sola_volta():
    argomenti = dict(event_id="e1", user_id="u1", name="backup_admin",
                     outcome="success", source_ip="192.168.206.129",
                     agent="curl/8.18.0", event_time="2026-11-05T15:48:41")
    assert db.save_alert(**argomenti) is True
    # lo stesso evento consegnato due volte non crea un secondo allarme
    assert db.save_alert(**argomenti) is False
    assert len(db.list_alerts()) == 1


def test_allarmi_dal_piu_recente_e_limite():
    for i in range(5):
        db.save_alert(event_id="e%d" % i, user_id="u1", name="esca",
                      outcome="failure", source_ip="10.0.0.%d" % i,
                      agent="curl", event_time="t%d" % i)
    allarmi = db.list_alerts(limit=3)
    assert [a["event_id"] for a in allarmi] == ["e4", "e3", "e2"]
