"""Honey-Stack - Gestore degli honeytoken.

Crea e rimuove gli utenti esca in Keystone, li registra nel database
e genera i file esca da lasciare dove un attaccante puo' trovarli.
Uso (dopo source openrc admin admin):
    python -m honeystack.manager create NOME [LUOGO]
    python -m honeystack.manager delete NOME
    python -m honeystack.manager list
"""
import os
import secrets
import string
import sys

import openstack

from honeystack import db

DECOY_PROJECT = os.environ.get("HONEYSTACK_PROJECT", "infra-ops")
DECOY_DIR = os.environ.get(
    "HONEYSTACK_DECOY_DIR", "/opt/stack/data/honey-stack/esche")

CLOUDS_YAML = """clouds:
  openstack:
    auth:
      auth_url: {auth_url}
      username: {username}
      password: {password}
      project_name: {project}
      user_domain_name: Default
      project_domain_name: Default
    region_name: RegionOne
    identity_api_version: 3
"""

OPENRC = """export OS_AUTH_URL={auth_url}
export OS_USERNAME={username}
export OS_PASSWORD={password}
export OS_PROJECT_NAME={project}
export OS_USER_DOMAIN_NAME=Default
export OS_PROJECT_DOMAIN_NAME=Default
export OS_IDENTITY_API_VERSION=3
"""


def genera_password(lunghezza=20):
    """Password casuale di sole lettere e cifre."""
    alfabeto = string.ascii_letters + string.digits
    return "".join(secrets.choice(alfabeto) for _ in range(lunghezza))


def _progetto_esche(conn):
    """Restituisce il progetto isolato delle esche, creandolo se manca."""
    progetto = conn.identity.find_project(DECOY_PROJECT)
    if progetto is None:
        progetto = conn.identity.create_project(
            name=DECOY_PROJECT, domain_id="default",
            description="Progetto isolato per honeytoken")
    return progetto


def _auth_url(conn):
    return conn.config.auth.get("auth_url") or os.environ["OS_AUTH_URL"]


def scrivi_file_esca(nome, password, progetto, auth_url):
    """Scrive clouds.yaml e openrc dell'esca; restituisce la cartella."""
    cartella = os.path.join(DECOY_DIR, nome)
    os.makedirs(cartella, mode=0o700, exist_ok=True)
    dati = dict(auth_url=auth_url, username=nome, password=password,
                project=progetto)
    for file, modello in (("clouds.yaml", CLOUDS_YAML), ("openrc", OPENRC)):
        percorso = os.path.join(cartella, file)
        with open(percorso, "w") as f:
            f.write(modello.format(**dati))
        os.chmod(percorso, 0o600)
    return cartella


def create_honeytoken(nome, luogo="", conn=None):
    """Crea l'utente esca, lo registra e genera i file esca."""
    conn = conn or openstack.connect()
    if conn.identity.find_user(nome) is not None:
        raise ValueError("Esiste gia' un utente chiamato " + nome)
    progetto = _progetto_esche(conn)
    password = genera_password()
    utente = conn.identity.create_user(
        name=nome, password=password, domain_id="default",
        default_project_id=progetto.id)
    db.add_honeytoken(utente.id, nome, progetto.id, luogo)
    return scrivi_file_esca(nome, password, progetto.name, _auth_url(conn))


def delete_honeytoken(nome, conn=None):
    """Elimina un honeytoken: solo utenti registrati come esca."""
    esca = next((h for h in db.list_honeytokens() if h["name"] == nome),
                None)
    if esca is None:
        raise ValueError(nome + " non e' un honeytoken attivo")
    conn = conn or openstack.connect()
    conn.identity.delete_user(esca["user_id"], ignore_missing=True)
    db.disable_honeytoken(esca["user_id"])


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    cmd = argv[1]
    try:
        if cmd == "create" and len(argv) >= 3:
            luogo = argv[3] if len(argv) > 3 else ""
            cartella = create_honeytoken(argv[2], luogo)
            print("Honeytoken creato:", argv[2])
            print("File esca in:", cartella)
        elif cmd == "delete" and len(argv) >= 3:
            delete_honeytoken(argv[2])
            print("Honeytoken eliminato:", argv[2])
        elif cmd == "list":
            for h in db.list_honeytokens():
                print(h["name"], h["user_id"], h["luogo"], h["created_at"])
        else:
            print(__doc__)
            return 1
    except ValueError as errore:
        print("Errore:", errore)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
