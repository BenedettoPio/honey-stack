"""Test del watcher (watcher.py) con eventi CADF reali di Keystone.

Gli eventi in dati/eventi_cadf.json sono stati catturati dalla VM
DevStack con tools/estrai_eventi.py (attacco da Kali e accessi veri).
"""
from honeystack import db, watcher


def consegna(evento):
    """Consegna un evento al watcher come farebbe oslo.messaging."""
    watcher.AuthEndpoint().info({}, "identity.keystone",
                                "identity.authenticate", evento, {})


def registra_esca(evento, nome="svc_backup"):
    db.add_honeytoken(evento["initiator"]["user_id"], nome, "p1", "luogo")


def test_password_sbagliata_su_esca(eventi):
    evento = eventi["esca_password_sbagliata"]
    registra_esca(evento)
    consegna(evento)
    [allarme] = db.list_alerts()
    assert allarme["name"] == "svc_backup"
    assert allarme["outcome"] == "failure"
    assert allarme["source_ip"] == evento["initiator"]["host"]["address"]
    assert allarme["agent"] == evento["initiator"]["host"]["agent"]
    assert allarme["event_time"] == evento["eventTime"]
    assert allarme["event_id"] == evento["id"]


def test_password_giusta_su_esca(eventi):
    evento = eventi["esca_password_giusta"]
    registra_esca(evento)
    consegna(evento)
    [allarme] = db.list_alerts()
    assert allarme["outcome"] == "success"


def test_utente_vero_ignorato(eventi):
    registra_esca(eventi["esca_password_giusta"])
    consegna(eventi["admin_reale"])
    assert db.list_alerts() == []


def test_password_sbagliata_di_utente_vero_ignorata(eventi):
    # un errore di battitura di un utente vero non e' un attacco all'esca
    registra_esca(eventi["esca_password_giusta"])
    consegna(eventi["utente_reale_password_sbagliata"])
    assert db.list_alerts() == []


def test_attacco_completo(eventi):
    # la sequenza vista da Kali: prima password sbagliata, poi giusta,
    # in mezzo agli accessi degli utenti veri
    registra_esca(eventi["esca_password_giusta"])
    for nome in ("admin_reale", "esca_password_sbagliata",
                 "utente_reale_password_sbagliata", "esca_password_giusta"):
        consegna(eventi[nome])
    esiti = [a["outcome"] for a in db.list_alerts()]
    assert esiti == ["success", "failure"]


def test_esca_disattivata_ignorata(eventi):
    evento = eventi["esca_password_giusta"]
    registra_esca(evento)
    db.disable_honeytoken(evento["initiator"]["user_id"])
    consegna(evento)
    assert db.list_alerts() == []


def test_evento_consegnato_due_volte(eventi):
    evento = eventi["esca_password_sbagliata"]
    registra_esca(evento)
    consegna(evento)
    consegna(evento)
    assert len(db.list_alerts()) == 1


def test_evento_malformato_non_ferma_il_watcher():
    consegna(None)
    consegna({"initiator": "testo invece di un oggetto"})
    assert db.list_alerts() == []


def test_indirizzo_rabbitmq_da_keystone_conf():
    url = watcher.leggi_transport_url()
    assert url == "rabbit://stackrabbit:secret@10.0.0.1:5672/"


def test_notifiche_non_configurate(tmp_path):
    vuoto = tmp_path / "keystone.conf"
    vuoto.write_text("[DEFAULT]\n")
    assert watcher.leggi_transport_url(str(vuoto)) is None
