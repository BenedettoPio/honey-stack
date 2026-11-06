"""Honey-Stack - Gestore degli honeytoken.

Crea e rimuove gli utenti esca in Keystone, li registra nel database
e genera i file esca da lasciare dove un attaccante puo' trovarli.
Uso:
    honey-stack create NOME [LUOGO]
    honey-stack create-vm NOME VM      (esca dentro una nuova VM)
    honey-stack delete NOME
    honey-stack list
"""
import os
import secrets
import string
import sys

from honeystack import cloud as cloud_mod
from honeystack import config, db

DECOY_PROJECT = config.get("decoy_project")
DECOY_DIR = config.get("decoy_dir")

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


def _nuova_esca(nome, cloud):
    """Crea l'utente esca in Keystone: (user_id, progetto, password)."""
    if cloud.utente_esiste(nome):
        raise ValueError("Esiste gia' un utente chiamato " + nome)
    progetto_id, progetto_nome = cloud.progetto_esche(DECOY_PROJECT)
    password = genera_password()
    user_id = cloud.crea_utente(nome, password, progetto_id)
    return user_id, progetto_id, progetto_nome, password


def create_honeytoken(nome, luogo="", cloud=None):
    """Crea l'utente esca, lo registra e genera i file esca."""
    cloud = cloud or cloud_mod.Cloud()
    user_id, progetto_id, progetto_nome, password = _nuova_esca(
        nome, cloud)
    db.add_honeytoken(user_id, nome, progetto_id, luogo)
    return scrivi_file_esca(nome, password, progetto_nome,
                            cloud.auth_url())


def script_avvio(clouds_yaml, utente):
    """Script eseguito al primo avvio della VM: scrive l'esca.

    E' uno script shell, non #cloud-config, perche' CirrOS esegue
    solo script; funziona anche con il cloud-init completo.
    """
    cartella = "/home/%s/.config/openstack" % utente
    return ("#!/bin/sh\n"
            "mkdir -p {c}\n"
            "cat > {c}/clouds.yaml << 'FINE_ESCA'\n"
            "{y}"
            "FINE_ESCA\n"
            "chown -R {u}:{u} /home/{u}/.config\n"
            "chmod 600 {c}/clouds.yaml\n").format(
                c=cartella, y=clouds_yaml, u=utente)


def create_honeytoken_vm(nome, vm, cloud=None):
    """Crea l'esca e una nuova VM che la contiene; restituisce i dati.

    Se la VM non parte, l'utente esca appena creato viene cancellato.
    """
    cloud = cloud or cloud_mod.Cloud()
    user_id, progetto_id, progetto_nome, password = _nuova_esca(
        nome, cloud)
    cartella = scrivi_file_esca(nome, password, progetto_nome,
                                cloud.auth_url())
    with open(os.path.join(cartella, "clouds.yaml")) as f:
        script = script_avvio(f.read(), config.get("vm_user"))
    try:
        vm_id, fisso, floating = cloud.crea_vm(
            vm, script,
            config.get("vm_image") or cloud.immagine_cirros(),
            config.get("vm_flavor"), config.get("vm_network"),
            cloud.gruppo_ssh(config.get("vm_security_group")),
            config.get("vm_floating_pool"))
    except Exception as errore:
        cloud.elimina_utente(user_id)
        raise ValueError("VM %s non creata: %s" % (vm, errore))
    indirizzi = ", ".join(ip for ip in (fisso, floating) if ip)
    luogo = "VM %s (%s) ~%s/.config/openstack/clouds.yaml" % (
        vm, indirizzi, config.get("vm_user"))
    db.add_honeytoken(user_id, nome, progetto_id, luogo)
    return {"vm_id": vm_id, "fisso": fisso, "floating": floating,
            "luogo": luogo}


def delete_honeytoken(nome, cloud=None):
    """Elimina un honeytoken: solo utenti registrati come esca."""
    esca = next((h for h in db.list_honeytokens() if h["name"] == nome),
                None)
    if esca is None:
        raise ValueError(nome + " non e' un honeytoken attivo")
    cloud = cloud or cloud_mod.Cloud()
    cloud.elimina_utente(esca["user_id"])
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
        elif cmd == "create-vm" and len(argv) >= 4:
            print("Creo la VM %s con l'esca %s (puo' volerci qualche "
                  "minuto)..." % (argv[3], argv[2]))
            dati = create_honeytoken_vm(argv[2], argv[3])
            print("Honeytoken creato:", argv[2])
            print("VM:", argv[3], dati["vm_id"])
            print("IP fisso:", dati["fisso"])
            print("Floating IP:", dati["floating"] or "nessuno")
            print("Luogo:", dati["luogo"])
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


def cli():
    """Punto di ingresso del comando honey-stack."""
    sys.exit(main(sys.argv))


if __name__ == "__main__":
    cli()
