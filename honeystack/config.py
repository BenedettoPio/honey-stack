"""Honey-Stack - Configurazione e log.

Legge /etc/honey-stack/honey-stack.conf con oslo.config (percorso
diverso con la variabile HONEYSTACK_CONF) e prepara i log con oslo.log,
come gli altri servizi di OpenStack. Senza la sezione [service_user]
si usano le credenziali dell'ambiente (source openrc).
"""
import os
import socket
import time
from urllib.parse import urlsplit

import openstack
from oslo_config import cfg
from oslo_log import log as logging

CONF_PATH = os.environ.get("HONEYSTACK_CONF",
                           "/etc/honey-stack/honey-stack.conf")

OPZIONI = [
    cfg.StrOpt("db_path",
               default="/opt/stack/data/honey-stack/honeystack.db",
               help="Database SQLite di honeytoken e allarmi."),
    cfg.StrOpt("decoy_dir", default="/opt/stack/data/honey-stack/esche",
               help="Cartella dei file esca (clouds.yaml, openrc)."),
    cfg.StrOpt("decoy_project", default="infra-ops",
               help="Progetto Keystone isolato delle esche."),
    cfg.PortOpt("dashboard_port", default=5050,
                help="Porta della dashboard e delle API."),
    cfg.StrOpt("keystone_conf", default="/etc/keystone/keystone.conf",
               help="Configurazione di Keystone (indirizzo di RabbitMQ)."),
    cfg.IntOpt("check_interval", default=60, min=10,
               help="Secondi tra un controllo delle esche e il "
                    "successivo."),
]

OPZIONI_UTENTE = [
    cfg.StrOpt("auth_url", help="Indirizzo di Keystone."),
    cfg.StrOpt("username", help="Utente di servizio di Honey-Stack."),
    cfg.StrOpt("password", secret=True,
               help="Password dell'utente di servizio."),
    cfg.StrOpt("project_name", default="service",
               help="Progetto dell'utente di servizio."),
    cfg.StrOpt("user_domain_name", default="Default",
               help="Dominio dell'utente di servizio."),
    cfg.StrOpt("project_domain_name", default="Default",
               help="Dominio del progetto dell'utente di servizio."),
]

CONF = cfg.ConfigOpts()
CONF.register_opts(OPZIONI)
CONF.register_opts(OPZIONI_UTENTE, group="service_user")
logging.register_options(CONF)
CONF([], project="honey-stack",
     default_config_files=[CONF_PATH] if os.path.exists(CONF_PATH) else [])

LOG = logging.getLogger(__name__)


def list_opts():
    """Opzioni di Honey-Stack, per oslo-config-generator."""
    return [("DEFAULT", OPZIONI), ("service_user", OPZIONI_UTENTE)]


def setup_log():
    """Attiva i log nel formato di OpenStack (watcher e dashboard)."""
    logging.setup(CONF, "honey-stack")


def get(chiave):
    """Valore di una voce di [DEFAULT]."""
    return CONF[chiave]


def ha_utente_di_servizio():
    return CONF.service_user.username is not None


def auth_url():
    """Indirizzo di Keystone."""
    if ha_utente_di_servizio():
        return CONF.service_user.auth_url
    return os.environ.get("OS_AUTH_URL", "http://127.0.0.1/identity")


def connessione():
    """Connessione a OpenStack con l'utente di servizio di Honey-Stack."""
    if not ha_utente_di_servizio():
        return openstack.connect()
    s = CONF.service_user
    return openstack.connect(
        auth_url=s.auth_url, username=s.username, password=s.password,
        project_name=s.project_name, user_domain_name=s.user_domain_name,
        project_domain_name=s.project_domain_name,
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
            LOG.warning("%s non raggiungibile (%s:%s), nuovo tentativo "
                        "tra %s s", nome, parti.hostname, porta, intervallo)
            time.sleep(intervallo)
