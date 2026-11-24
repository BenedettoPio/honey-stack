"""Test delle API REST (app.py), con OpenStack finto."""
import pytest

from honeystack import app as app_mod
from honeystack import db, manager

ADMIN = {"X-Auth-Token": "token-admin"}


@pytest.fixture
def client(cloud_finto):
    app_mod.app.config["TESTING"] = True
    return app_mod.app.test_client()


def test_descrizione_del_servizio_senza_token(client):
    risposta = client.get("/")
    assert risposta.status_code == 200
    assert risposta.get_json()["versions"] == ["v1"]


@pytest.mark.parametrize("metodo,indirizzo", [
    ("get", "/api/v1/alerts"),
    ("get", "/api/v1/honeytokens"),
    ("post", "/api/v1/honeytokens"),
    ("delete", "/api/v1/honeytokens/svc_backup"),
    ("get", "/api/v1/honeytokens/svc_backup/files/clouds.yaml"),
    ("get", "/api/v1/quarantines"),
    ("post", "/api/v1/quarantines/1/release"),
])
def test_ogni_api_richiede_un_token_admin(client, metodo, indirizzo):
    senza = getattr(client, metodo)(indirizzo)
    non_admin = getattr(client, metodo)(
        indirizzo, headers={"X-Auth-Token": "token-utente"})
    assert senza.status_code == 401
    assert non_admin.status_code == 401


def test_allarmi_con_gravita_e_luogo(client):
    manager.create_honeytoken("svc_backup", "Kali ~/Downloads")
    db.save_alert(event_id="e1", user_id="u1", name="svc_backup",
                  outcome="success", source_ip="192.168.206.129",
                  agent="curl", event_time="t1")
    db.save_alert(event_id="e2", user_id="u1", name="svc_backup",
                  outcome="failure", source_ip="192.168.206.129",
                  agent="curl", event_time="t2")
    allarmi = client.get("/api/v1/alerts", headers=ADMIN).get_json()
    assert {a["outcome"]: a["gravita"] for a in allarmi} == {
        "success": "GRAVE", "failure": "ATTENZIONE"}
    assert {a["luogo"] for a in allarmi} == {"Kali ~/Downloads"}


@pytest.mark.parametrize("tipo", ["ruolo_assegnato", "brute_force",
                                  "ricognizione", "quarantena"])
def test_allarmi_gravi_di_controllo_correlazione_e_quarantena(client, tipo):
    db.save_alert(event_id="k1", user_id="-", name="svc_backup",
                  outcome=tipo, source_ip=None, agent="dettaglio",
                  event_time="2026-11-06T12:00:00")
    allarmi = client.get("/api/v1/alerts", headers=ADMIN).get_json()
    assert allarmi[0]["gravita"] == "GRAVE"


def test_crea_elenca_ed_elimina_honeytoken(client, cloud_finto):
    risposta = client.post("/api/v1/honeytokens", headers=ADMIN,
                           json={"name": "svc_backup", "location": "Kali"})
    assert risposta.status_code == 201
    assert risposta.get_json()["luogo"] == "Kali"
    elenco = client.get("/api/v1/honeytokens", headers=ADMIN).get_json()
    assert [h["name"] for h in elenco] == ["svc_backup"]
    risposta = client.delete("/api/v1/honeytokens/svc_backup",
                             headers=ADMIN)
    assert risposta.status_code == 204
    assert db.list_honeytokens() == []
    assert ("elimina_utente", "id-svc_backup") in cloud_finto.chiamate


@pytest.mark.parametrize("dati", [{"location": "Kali"}, {"name": ""},
                                  {"name": "../etc"}, {"name": "a b"},
                                  {"name": ".nascosta"}, {"name": "x" * 65}])
def test_creazione_con_nome_non_valido(client, cloud_finto, dati):
    risposta = client.post("/api/v1/honeytokens", headers=ADMIN, json=dati)
    assert risposta.status_code == 400
    assert not any(c[0] == "crea_utente" for c in cloud_finto.chiamate)


def test_creazione_duplicata(client):
    client.post("/api/v1/honeytokens", headers=ADMIN,
                json={"name": "svc_backup"})
    assert client.post("/api/v1/honeytokens", headers=ADMIN,
                       json={"name": "svc_backup"}).status_code == 409


def test_eliminazione_di_un_utente_che_non_e_esca(client, cloud_finto):
    risposta = client.delete("/api/v1/honeytokens/admin", headers=ADMIN)
    assert risposta.status_code == 404
    assert not any(c[0] == "elimina_utente" for c in cloud_finto.chiamate)


def test_scarica_file_esca(client):
    manager.create_honeytoken("svc_backup")
    risposta = client.get("/api/v1/honeytokens/svc_backup/files/clouds.yaml",
                          headers=ADMIN)
    assert risposta.status_code == 200
    assert b"username: svc_backup" in risposta.data
    assert "attachment" in risposta.headers["Content-Disposition"]


@pytest.mark.parametrize("indirizzo", [
    "/api/v1/honeytokens/svc_backup/files/passwd",          # file non previsto
    "/api/v1/honeytokens/sconosciuta/files/clouds.yaml",    # esca inesistente
    "/api/v1/honeytokens/..%2F..%2Fetc/files/clouds.yaml",  # uscita dalla cartella
])
def test_download_controllato(client, indirizzo):
    manager.create_honeytoken("svc_backup")
    assert client.get(indirizzo, headers=ADMIN).status_code == 404


def test_quarantene_e_rilascio(client, cloud_finto):
    cloud_finto.gruppi_porta["porta-1"] = ["id-honey-quarantena"]
    db.add_quarantine(port_id="porta-1", server_id="vm-1",
                      server_name="web-01", source_ip="172.24.4.124",
                      honeytoken="svc_deploy",
                      original_groups='["sg-originale"]')
    elenco = client.get("/api/v1/quarantines", headers=ADMIN).get_json()
    assert [q["server_name"] for q in elenco] == ["web-01"]
    risposta = client.post("/api/v1/quarantines/%d/release" % elenco[0]["id"],
                           headers=ADMIN)
    assert risposta.get_json() == {"server_name": "web-01"}
    assert db.list_quarantine() == []
    assert cloud_finto.gruppi_porta["porta-1"] == ["sg-originale"]


def test_rilascio_di_una_quarantena_che_non_esiste(client):
    risposta = client.post("/api/v1/quarantines/99/release", headers=ADMIN)
    assert risposta.status_code == 404


def test_rilascio_per_id_non_per_nome_della_vm(client, cloud_finto):
    # una VM chiamata "7" non deve essere scambiata per la voce 7
    db.add_quarantine(port_id="porta-1", server_id="vm-1", server_name="2",
                      source_ip="172.24.4.124", honeytoken="svc_deploy",
                      original_groups='["sg-originale"]')
    risposta = client.post("/api/v1/quarantines/2/release", headers=ADMIN)
    assert risposta.status_code == 404
    assert len(db.list_quarantine()) == 1


def test_crea_honeytoken_dentro_una_vm(client, cloud_finto):
    risposta = client.post("/api/v1/honeytokens", headers=ADMIN,
                           json={"name": "svc_deploy", "vm": "web-01"})
    assert risposta.status_code == 201
    dati = risposta.get_json()
    assert dati["name"] == "svc_deploy"
    assert dati["vm"]["name"] == "web-01"
    assert dati["vm"]["floating"] == "172.24.4.115"
    assert dati["luogo"].startswith("VM web-01")


@pytest.mark.parametrize("vm", ["", "a b", "../x"])
def test_crea_honeytoken_con_nome_della_vm_non_valido(client, cloud_finto,
                                                      vm):
    risposta = client.post("/api/v1/honeytokens", headers=ADMIN,
                           json={"name": "svc_deploy", "vm": vm})
    assert risposta.status_code == 400
    assert cloud_finto.chiamate == []


def test_vm_non_creata(client, cloud_finto):
    # errore di Nova: 502, e l'utente esca appena creato viene cancellato
    cloud_finto.vm_rotta = True
    risposta = client.post("/api/v1/honeytokens", headers=ADMIN,
                           json={"name": "svc_deploy", "vm": "web-01"})
    assert risposta.status_code == 502
    assert "non creata" in risposta.get_json()["error"]
    assert ("elimina_utente", "id-svc_deploy") in cloud_finto.chiamate
