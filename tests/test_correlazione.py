"""Test della correlazione degli attacchi (correlazione.py).

Gli attacchi sono costruiti dagli eventi CADF reali catturati da Kali,
cambiando solo l'ID dell'evento (e, dove serve, l'esca o l'IP).
"""
import copy
import itertools

from honeystack import correlazione, db, watcher

_contatore = itertools.count()


def attacco(eventi, caso="esca_password_sbagliata", ip=None, user_id=None):
    """Consegna al watcher una copia dell'evento reale con un ID nuovo."""
    evento = copy.deepcopy(eventi[caso])
    evento["id"] = "evento-%d" % next(_contatore)
    if ip:
        evento["initiator"]["host"]["address"] = ip
    if user_id:
        evento["initiator"]["user_id"] = user_id
    watcher.AuthEndpoint().info({}, "identity.keystone",
                                "identity.authenticate", evento, {})


def registra_esche(eventi):
    reale = eventi["esca_password_sbagliata"]["initiator"]["user_id"]
    db.add_honeytoken(reale, "svc_backup", "p1", "Kali ~/Downloads")
    db.add_honeytoken("id-db_readonly", "db_readonly", "p1", "VM web-01")


def correlati(tipo=None):
    tipi = ("brute_force", "ricognizione")
    return [a for a in db.list_alerts(100)
            if a["outcome"] in tipi and (tipo is None or a["outcome"] == tipo)]


def test_pochi_tentativi_nessuna_correlazione(eventi):
    registra_esche(eventi)
    for _ in range(4):
        attacco(eventi)
    assert correlati() == []


def test_brute_force_alla_quinta_password_sbagliata(eventi):
    registra_esche(eventi)
    for _ in range(5):
        attacco(eventi)
    [allarme] = correlati("brute_force")
    assert allarme["source_ip"] == "192.168.206.129"
    assert allarme["name"] == "svc_backup"
    assert "5 password sbagliate" in allarme["agent"]


def test_brute_force_segnalato_una_sola_volta(eventi):
    registra_esche(eventi)
    for _ in range(9):
        attacco(eventi)
    assert len(correlati("brute_force")) == 1


def test_ip_diversi_non_si_sommano(eventi):
    registra_esche(eventi)
    for ip in ("10.0.0.1", "10.0.0.2", "10.0.0.3"):
        for _ in range(4):
            attacco(eventi, ip=ip)
    assert correlati() == []


def test_ricognizione_su_due_esche(eventi):
    registra_esche(eventi)
    attacco(eventi)
    attacco(eventi, user_id="id-db_readonly")
    [allarme] = correlati("ricognizione")
    assert allarme["name"] == "db_readonly, svc_backup"
    assert "2 esche diverse" in allarme["agent"]


def test_stessa_esca_non_e_ricognizione(eventi):
    registra_esche(eventi)
    attacco(eventi)
    attacco(eventi, caso="esca_password_giusta")
    assert correlati("ricognizione") == []


def test_tentativi_vecchi_fuori_dalla_finestra(eventi):
    registra_esche(eventi)
    # 4 tentativi di un'ora fa: non contano per il brute force di adesso
    for i in range(4):
        db.save_alert(event_id="vecchio-%d" % i, user_id="u", name="svc_backup",
                      outcome="failure", source_ip="192.168.206.129",
                      agent="curl", event_time="t")
    with db.connect() as conn:
        conn.execute("UPDATE alerts SET received_at = "
                     "'2026-01-01T00:00:00+00:00'")
    attacco(eventi)
    assert correlati() == []


def test_utente_vero_non_fa_correlazione(eventi):
    registra_esche(eventi)
    for _ in range(6):
        attacco(eventi, caso="utente_reale_password_sbagliata")
    assert correlati() == []


def test_senza_ip_nessuna_analisi():
    assert correlazione.analizza(None) == []
