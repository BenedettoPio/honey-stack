"""Ambiente dei test: configurazione, database e file esca temporanei.

Le variabili d'ambiente vanno impostate prima di importare honeystack,
perche' config.py legge la configurazione all'importazione. I test non
toccano mai /etc/honey-stack ne' il database vero.
"""
import json
import os
import pathlib
import shutil
import tempfile

import pytest

CARTELLA = pathlib.Path(tempfile.mkdtemp(prefix="honeystack-test-"))
DATI = pathlib.Path(__file__).parent / "dati"
AUTH_URL = "http://keystone.test/identity"

(CARTELLA / "keystone.conf").write_text(
    "[oslo_messaging_notifications]\n"
    "transport_url = rabbit://stackrabbit:secret@10.0.0.1:5672/\n")
(CARTELLA / "honey-stack.conf").write_text(
    "[DEFAULT]\n"
    "db_path = {0}/honeystack.db\n"
    "decoy_dir = {0}/esche\n"
    "decoy_project = infra-ops\n"
    "dashboard_port = 6060\n"
    "keystone_conf = {0}/keystone.conf\n".format(CARTELLA))
os.environ["HONEYSTACK_CONF"] = str(CARTELLA / "honey-stack.conf")
os.environ["OS_AUTH_URL"] = AUTH_URL


class CloudFinto:
    """Sostituisce cloud.Cloud: niente OpenStack, registra le chiamate."""

    def __init__(self):
        self.utenti = {}
        self.chiamate = []
        self.password = {}
        self.admin = {"admin": "secret"}
        self.token_validi = {"token-admin"}

    def auth_url(self):
        return AUTH_URL

    def utente_esiste(self, nome):
        return nome in self.utenti or nome in self.admin

    def progetto_esche(self, nome):
        self.chiamate.append(("progetto_esche", nome))
        return "id-progetto-" + nome, nome

    def crea_utente(self, nome, password, progetto_id):
        self.chiamate.append(("crea_utente", nome, progetto_id))
        self.utenti[nome] = "id-" + nome
        self.password[nome] = password
        return self.utenti[nome]

    def elimina_utente(self, user_id):
        self.chiamate.append(("elimina_utente", user_id))

    def login_admin(self, utente, password):
        return self.admin.get(utente) == password

    def token_admin(self, token):
        return token in self.token_validi


@pytest.fixture(autouse=True)
def ambiente_pulito():
    """Ogni test parte senza database e senza file esca."""
    from honeystack import config
    db = pathlib.Path(config.get("db_path"))
    if db.exists():
        db.unlink()
    shutil.rmtree(config.get("decoy_dir"), ignore_errors=True)
    yield


@pytest.fixture
def cloud_finto(monkeypatch):
    """Mette CloudFinto al posto di cloud.Cloud in tutto il codice."""
    from honeystack import cloud
    finto = CloudFinto()
    monkeypatch.setattr(cloud, "Cloud", lambda *a, **k: finto)
    return finto


@pytest.fixture
def eventi():
    """Eventi CADF identity.authenticate catturati da Keystone."""
    with open(DATI / "eventi_cadf.json") as f:
        return json.load(f)
