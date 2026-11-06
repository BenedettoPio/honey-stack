"""Test della dashboard e delle API (app.py), con OpenStack finto."""
import pytest

from honeystack import app as app_mod
from honeystack import db, manager


@pytest.fixture
def client(cloud_finto):
    app_mod.app.config["TESTING"] = True
    return app_mod.app.test_client()


def accedi(client, utente="admin", password="secret"):
    return client.post("/login", data={"utente": utente,
                                       "password": password})


def test_senza_login_rimanda_al_login(client):
    risposta = client.get("/")
    assert risposta.status_code == 302
    assert "/login" in risposta.headers["Location"]


def test_login_admin(client):
    assert accedi(client).status_code == 302
    risposta = client.get("/")
    assert risposta.status_code == 200
    assert b"Honeytoken attivi" in risposta.data


def test_login_rifiutato(client):
    risposta = accedi(client, "demo", "secret")
    assert risposta.status_code == 200
    assert b"Credenziali non valide" in risposta.data
    assert client.get("/").status_code == 302


def test_crea_ed_elimina_dalla_dashboard(client, cloud_finto):
    accedi(client)
    client.post("/honeytokens", data={"nome": "svc_backup",
                                      "luogo": "Kali"})
    assert [h["name"] for h in db.list_honeytokens()] == ["svc_backup"]
    client.post("/honeytokens/svc_backup/delete")
    assert db.list_honeytokens() == []
    assert ("elimina_utente", "id-svc_backup") in cloud_finto.chiamate


def test_scarica_file_esca(client):
    manager.create_honeytoken("svc_backup")
    accedi(client)
    risposta = client.get("/honeytokens/svc_backup/clouds.yaml")
    assert risposta.status_code == 200
    assert b"username: svc_backup" in risposta.data


@pytest.mark.parametrize("indirizzo", [
    "/honeytokens/svc_backup/passwd",          # file non previsto
    "/honeytokens/sconosciuta/clouds.yaml",    # esca che non esiste
    "/honeytokens/..%2F..%2Fetc/clouds.yaml",  # tentativo di uscire
])
def test_download_controllato(client, indirizzo):
    manager.create_honeytoken("svc_backup")
    accedi(client)
    assert client.get(indirizzo).status_code == 404


def test_api_senza_token(client):
    risposta = client.get("/api/v1/alerts")
    assert risposta.status_code == 401


def test_api_con_token_non_admin(client):
    risposta = client.get("/api/v1/alerts",
                          headers={"X-Auth-Token": "token-utente"})
    assert risposta.status_code == 401


def test_api_allarmi_con_gravita(client):
    db.save_alert(event_id="e1", user_id="u1", name="svc_backup",
                  outcome="success", source_ip="192.168.206.129",
                  agent="curl", event_time="t1")
    db.save_alert(event_id="e2", user_id="u1", name="svc_backup",
                  outcome="failure", source_ip="192.168.206.129",
                  agent="curl", event_time="t2")
    risposta = client.get("/api/v1/alerts",
                          headers={"X-Auth-Token": "token-admin"})
    assert risposta.status_code == 200
    gravita = {a["outcome"]: a["gravita"] for a in risposta.get_json()}
    assert gravita == {"success": "GRAVE", "failure": "ATTENZIONE"}


def test_api_honeytoken(client):
    manager.create_honeytoken("svc_backup", "Kali")
    risposta = client.get("/api/v1/honeytokens",
                          headers={"X-Auth-Token": "token-admin"})
    assert [h["name"] for h in risposta.get_json()] == ["svc_backup"]


def test_allarme_del_controllo_in_dashboard(client):
    db.save_alert(event_id="c1", user_id="u1", name="svc_backup",
                  outcome="ruolo_assegnato", source_ip=None,
                  agent="ruolo member su project demo: rimosso",
                  event_time="2026-11-06T12:00:00")
    accedi(client)
    pagina = client.get("/").data.decode()
    assert 'class="grave"' in pagina
    assert "ruolo member su project demo" in pagina
    assert "None" not in pagina


def test_allarme_di_correlazione_in_dashboard(client):
    db.save_alert(event_id="k1", user_id="-", name="svc_backup",
                  outcome="brute_force", source_ip="192.168.206.129",
                  agent="5 password sbagliate in 5 minuti",
                  event_time="2026-11-06T12:00:00")
    accedi(client)
    pagina = client.get("/").data.decode()
    assert 'class="grave"' in pagina
    assert "5 password sbagliate in 5 minuti" in pagina
