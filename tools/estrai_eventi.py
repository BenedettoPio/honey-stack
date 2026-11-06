"""Estrae dal journal del watcher gli eventi CADF reali per i test.

Il watcher, con debug = True in /etc/honey-stack/honey-stack.conf,
scrive ogni evento identity.authenticate come "Evento CADF: {...}".
Questo script legge quelle righe da standard input e salva in un file
JSON il primo evento di ogni caso utile ai test.

Uso:
    sudo journalctl -u devstack@honey-stack-watcher --since "..." -o cat \\
        | python tools/estrai_eventi.py ESCA tests/dati/eventi_cadf.json
"""
import json
import sys

MARCATORE = "Evento CADF: "


def casi(esca):
    """Nome del caso -> condizione sull'evento."""
    def utente(e):
        return e.get("initiator", {}).get("name")
    return {
        "esca_password_sbagliata":
            lambda e: utente(e) == esca and e.get("outcome") == "failure",
        "esca_password_giusta":
            lambda e: utente(e) == esca and e.get("outcome") == "success",
        "admin_reale":
            lambda e: utente(e) == "admin" and e.get("outcome") == "success",
        "utente_reale_password_sbagliata":
            lambda e: utente(e) == "demo" and e.get("outcome") == "failure",
    }


def leggi_eventi(righe):
    decoder = json.JSONDecoder()
    for riga in righe:
        if MARCATORE in riga:
            testo = riga.split(MARCATORE, 1)[1]
            # oslo.log aggiunge in coda il nome della funzione: si ignora
            evento, _ = decoder.raw_decode(testo)
            yield evento


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 1
    esca, destinazione = argv[1], argv[2]
    trovati = {}
    for evento in leggi_eventi(sys.stdin):
        for nome, condizione in casi(esca).items():
            if nome not in trovati and condizione(evento):
                trovati[nome] = evento
    mancanti = sorted(set(casi(esca)) - set(trovati))
    with open(destinazione, "w") as f:
        json.dump(trovati, f, indent=2, sort_keys=True)
        f.write("\n")
    print("Salvati:", ", ".join(sorted(trovati)))
    if mancanti:
        print("Mancano:", ", ".join(mancanti))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
