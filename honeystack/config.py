"""Honey-Stack - Configurazione.

Legge /etc/honey-stack/honey-stack.conf (percorso diverso con la
variabile HONEYSTACK_CONF). Se il file o una voce mancano valgono i
valori predefiniti; senza la sezione [service_user] si usano le
credenziali dell'ambiente (source openrc).
"""
import configparser
import os
import socket
import time
from urllib.parse import urlsplit

import openstack

CONF_PATH = os.environ.get("HONEYSTACK_CONF",
                           "/etc/honey-stack/honey-stack.conf")

PREDEFINITI = {
    "db_path": "/opt/stack/data/honey-stack/honeystack.db",
    "decoy_dir": "/opt/stack/data/honey-stack/esche",
    "decoy_project": "infra-ops",
    "dashboard_port": "5050",
    "keystone_conf": "/etc/keystone/keystone.conf",
}

_parser = configparser.ConfigParser(interpolation=None)
_parser.read(CONF_PATH)


def get(chiave):
    """Valore di una voce di [DEFAULT]."""
    return _parser.get("DEFAULT", chiave, fallback=PREDEFINITI[chiave])


def ha_utente_di_servizio():
    return _parser.has_section("service_user")


def auth_url():
    """Indirizzo di Keystone."""
    if ha_utente_di_servizio():
        return _parser.get("service_user", "auth_url")
    return os.environ.get("OS_AUTH_URL", "http://127.0.0.1/identity")


def connessione():
    """Connessione a OpenStack con l'utente di servizio di Honey-Stack."""
    if not ha_utente_di_servizio():
        return openstack.connect()
    s = _parser["service_user"]
    return openstack.connect(
        auth_url=s["auth_url"], username=s["username"],
        password=s["password"], project_name=s["project_name"],
        user_domain_name=s.get("user_domain_name", "Default"),
        project_domain_name=s.get("project_domain_name", "Default"),
        load_yaml_config=False, load_envvars=False)


def attendi(url, nome, porta_predefinita=80, intervallo=5):
    """Aspetta che il servizio all'indirizzo url accetti connessioni."""
    parti = urlsplit(url)
    porta = parti.port or porta_predefinita
    while True:
        try:
            socket.create_connection((parti.hostname, porta), 3).close()
            return
        except OSError:
            print("{} non raggiungibile ({}:{}), nuovo tentativo tra {} s"
                  .format(nome, parti.hostname, porta, intervallo),
                  flush=True)
            time.sleep(intervallo)
