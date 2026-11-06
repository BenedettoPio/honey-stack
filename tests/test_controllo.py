"""Test del controllo periodico delle esche (controllo.py)."""
import threading

from honeystack import cloud, controllo, db

RUOLO_MEMBER = {"ruolo_id": "r1", "ruolo": "member", "ambito": "project",
                "ambito_id": "p-demo", "ambito_nome": "demo"}


def esca(user_id="u1", nome="svc_backup"):
    db.add_honeytoken(user_id, nome, "p1", "luogo")
    return user_id


def tipi_allarme():
    return [a["outcome"] for a in db.list_alerts()]


def test_esca_in_ordine_nessun_allarme(cloud_finto):
    esca()
    controllo.controlla_esche(cloud_finto)
    assert db.list_alerts() == []
    assert cloud_finto.chiamate == []


def test_ruolo_assegnato_all_esca(cloud_finto):
    uid = esca()
    cloud_finto.ruoli[uid] = [dict(RUOLO_MEMBER)]
    controllo.controlla_esche(cloud_finto)
    [allarme] = db.list_alerts()
    assert allarme["outcome"] == "ruolo_assegnato"
    assert "member" in allarme["agent"] and "demo" in allarme["agent"]
    assert allarme["source_ip"] is None
    assert ("rimuovi_ruolo", uid, "member") in cloud_finto.chiamate
    # ruolo rimosso: al giro successivo nessun nuovo allarme
    controllo.controlla_esche(cloud_finto)
    assert len(db.list_alerts()) == 1


def test_esca_inserita_in_un_gruppo(cloud_finto):
    uid = esca()
    cloud_finto.gruppi[uid] = [{"id": "g1", "nome": "operatori"}]
    controllo.controlla_esche(cloud_finto)
    assert tipi_allarme() == ["gruppo_assegnato"]
    assert ("rimuovi_da_gruppo", uid, "g1") in cloud_finto.chiamate


def test_esca_disabilitata_viene_riattivata(cloud_finto):
    uid = esca()
    cloud_finto.stati[uid] = "disattivato"
    controllo.controlla_esche(cloud_finto)
    assert tipi_allarme() == ["esca_disattivata"]
    assert ("riattiva_utente", uid) in cloud_finto.chiamate
    assert cloud_finto.stato_utente(uid) == "attivo"


def test_esca_cancellata_fuori_da_honey_stack(cloud_finto):
    uid = esca()
    cloud_finto.stati[uid] = "assente"
    controllo.controlla_esche(cloud_finto)
    assert tipi_allarme() == ["esca_eliminata"]
    # non piu' attiva: non viene controllata di nuovo
    assert db.get_active_honeytoken(uid) is None
    controllo.controlla_esche(cloud_finto)
    assert len(db.list_alerts()) == 1


def test_un_errore_non_ferma_le_altre_esche(cloud_finto, monkeypatch):
    esca("u1", "esca_rotta")
    uid = esca("u2", "esca_buona")
    cloud_finto.ruoli[uid] = [dict(RUOLO_MEMBER)]
    originale = cloud_finto.stato_utente

    def stato(user_id):
        if user_id == "u1":
            raise RuntimeError("Keystone non risponde")
        return originale(user_id)
    monkeypatch.setattr(cloud_finto, "stato_utente", stato)
    controllo.controlla_esche(cloud_finto)
    assert [a["name"] for a in db.list_alerts()] == ["esca_buona"]


def test_solo_le_esche_attive(cloud_finto):
    uid = esca()
    db.disable_honeytoken(uid)
    cloud_finto.ruoli[uid] = [dict(RUOLO_MEMBER)]
    controllo.controlla_esche(cloud_finto)
    assert db.list_alerts() == []


def test_lo_scheduler_si_ferma(cloud_finto):
    uid = esca()
    cloud_finto.ruoli[uid] = [dict(RUOLO_MEMBER)]
    fermati = threading.Event()
    fermati.set()
    # con l'arresto gia' richiesto fa un solo controllo e termina
    controllo.ciclo(fermati, intervallo=10)
    assert tipi_allarme() == ["ruolo_assegnato"]


class _Assegnazione:
    def __init__(self, role, scope):
        self.role, self.scope = role, scope


class _Identity:
    def role_assignments(self, **query):
        assert query == {"user_id": "u1", "include_names": True}
        return [
            _Assegnazione({"id": "r1", "name": "member"},
                          {"project": {"id": "p1", "name": "demo",
                                       "domain": {"id": "default"}}}),
            _Assegnazione({"id": "r2", "name": "admin"},
                          {"system": {"all": True}}),
        ]


class _Conn:
    identity = _Identity()


def test_lettura_dei_ruoli_da_keystone():
    # formato della risposta di Keystone con include_names
    ruoli = cloud.Cloud(conn=_Conn()).ruoli_utente("u1")
    assert ruoli == [
        {"ruolo_id": "r1", "ruolo": "member", "ambito": "project",
         "ambito_id": "p1", "ambito_nome": "demo"},
        {"ruolo_id": "r2", "ruolo": "admin", "ambito": "system",
         "ambito_id": "all", "ambito_nome": "all"},
    ]
