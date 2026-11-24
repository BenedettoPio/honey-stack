"""Honey-Stack - Comando honey-stack.

Client delle API REST di Honey-Stack, come il client openstack lo e' delle
API degli altri servizi: non usa il database ne' l'utente di servizio.
Le credenziali sono quelle dell'operatore (source openrc admin admin) e
l'indirizzo delle API si legge dal catalogo di Keystone (servizio di tipo
"deception"), come fanno i pannelli di Horizon.
Uso:
    honey-stack create NOME [LUOGO]
    honey-stack create-vm NOME VM      (esca dentro una nuova VM)
    honey-stack files NOME [CARTELLA]  (scarica clouds.yaml e openrc)
    honey-stack delete NOME
    honey-stack list
    honey-stack alerts
    honey-stack quarantine-list        (VM in quarantena)
    honey-stack release VM             (rilascia una VM: nome, IP o ID)
"""
import json
import os
import sys
from urllib.parse import quote

TIPO_SERVIZIO = "deception"
FILE_ESCA = ("clouds.yaml", "openrc")
# creare una VM con l'esca richiede qualche minuto
ATTESA = 60
ATTESA_VM = 900


class Errore(Exception):
    """Risposta di errore delle API, con il loro messaggio."""


def _sessione():
    """Sessione Keystone con le credenziali dell'ambiente (openrc)."""
    import openstack
    return openstack.connect().session


def richiesta(metodo, percorso, dati=None, attesa=ATTESA):
    """Chiama le API di Honey-Stack con il token dell'operatore.

    Restituisce (codice HTTP, corpo in byte). L'indirizzo delle API viene
    dal catalogo, il token lo aggiunge la sessione di Keystone.
    """
    try:
        risposta = _sessione().request(
            percorso, metodo, json=dati, timeout=attesa, raise_exc=False,
            endpoint_filter={"service_type": TIPO_SERVIZIO,
                             "interface": "public"})
    except Exception as errore:
        # credenziali mancanti, servizio deception assente, API spente
        raise Errore("API di Honey-Stack non raggiungibili (serve source "
                     "openrc admin admin): %s" % errore)
    return risposta.status_code, risposta.content


def _chiama(metodo, percorso, dati=None, attesa=ATTESA):
    """Come richiesta, ma un codice di errore diventa un'eccezione."""
    codice, corpo = richiesta(metodo, percorso, dati=dati, attesa=attesa)
    if codice >= 400:
        try:
            messaggio = json.loads(corpo)["error"]
        except (ValueError, KeyError, TypeError):
            messaggio = "HTTP %s" % codice
        raise Errore(messaggio)
    return corpo


def _json(metodo, percorso, dati=None, attesa=ATTESA):
    return json.loads(_chiama(metodo, percorso, dati=dati, attesa=attesa))


def scarica_file_esca(nome, cartella):
    """Salva clouds.yaml e openrc dell'esca in cartella (permessi 600)."""
    os.makedirs(cartella, mode=0o700, exist_ok=True)
    for file in FILE_ESCA:
        contenuto = _chiama("GET", "/api/v1/honeytokens/%s/files/%s"
                            % (quote(nome), file))
        percorso = os.path.join(cartella, file)
        with open(percorso, "wb") as f:
            f.write(contenuto)
        os.chmod(percorso, 0o600)
    return cartella


def quarantena_attiva(vm_o_ip):
    """Quarantena attiva per nome della VM, IP o id della voce."""
    for voce in _json("GET", "/api/v1/quarantines"):
        if vm_o_ip in (voce["server_name"], voce["source_ip"],
                       str(voce["id"])):
            return voce
    return None


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    cmd = argv[1]
    try:
        if cmd == "create" and len(argv) >= 3:
            luogo = argv[3] if len(argv) > 3 else ""
            _json("POST", "/api/v1/honeytokens",
                  dati={"name": argv[2], "location": luogo})
            print("Honeytoken creato:", argv[2])
            print("File esca: honey-stack files %s, oppure da Horizon"
                  % argv[2])
        elif cmd == "files" and len(argv) >= 3:
            cartella = argv[3] if len(argv) > 3 else argv[2]
            print("File esca in:", scarica_file_esca(argv[2], cartella))
        elif cmd == "create-vm" and len(argv) >= 4:
            print("Creo la VM %s con l'esca %s (puo' volerci qualche "
                  "minuto)..." % (argv[3], argv[2]))
            esca = _json("POST", "/api/v1/honeytokens",
                         dati={"name": argv[2], "vm": argv[3]},
                         attesa=ATTESA_VM)
            vm = esca["vm"]
            print("Honeytoken creato:", argv[2])
            print("VM:", argv[3], vm["vm_id"])
            print("IP fisso:", vm["fisso"])
            print("Floating IP:", vm["floating"] or "nessuno")
            print("Luogo:", vm["luogo"])
        elif cmd == "delete" and len(argv) >= 3:
            _chiama("DELETE", "/api/v1/honeytokens/%s" % quote(argv[2]))
            print("Honeytoken eliminato:", argv[2])
        elif cmd == "list":
            for h in _json("GET", "/api/v1/honeytokens"):
                print(h["name"], h["user_id"], h["luogo"], h["created_at"])
        elif cmd == "alerts":
            for a in _json("GET", "/api/v1/alerts"):
                print(a["id"], a["event_time"], a["gravita"], a["name"],
                      a["outcome"], a["source_ip"], a["agent"])
        elif cmd == "quarantine-list":
            for q in _json("GET", "/api/v1/quarantines"):
                print(q["server_name"], q["source_ip"], q["honeytoken"],
                      q["started_at"])
        elif cmd == "release" and len(argv) >= 3:
            voce = quarantena_attiva(argv[2])
            if voce is None:
                raise Errore(argv[2] + " non e' in quarantena")
            vm = _json("POST", "/api/v1/quarantines/%d/release"
                       % voce["id"])["server_name"]
            print("VM rilasciata, gruppi originali ripristinati:", vm)
        else:
            print(__doc__)
            return 1
    except Errore as errore:
        print("Errore:", errore)
        return 1
    return 0


def cli():
    """Punto di ingresso del comando honey-stack."""
    sys.exit(main(sys.argv))


if __name__ == "__main__":
    cli()
