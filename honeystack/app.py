"""Honey-Stack - API REST.

Espone esche, allarmi e quarantene al pannello di Horizon (e a chiunque
abbia un token Keystone con ruolo admin). Ogni richiesta deve portare
il token nell'intestazione X-Auth-Token: e' quello dell'utente entrato
in Horizon, quindi non serve un secondo login.
Avvio: honey-stack-dashboard (servizio devstack@honey-stack-dashboard)
"""
import functools
import os
import re

from flask import Flask, abort, jsonify, request, send_file

from honeystack import cloud, config, db, manager, quarantena

app = Flask(__name__)

AUTH_URL = config.auth_url()
PORTA = int(config.get("dashboard_port"))
FILE_ESCA = ("clouds.yaml", "openrc")
# nome dell'esca: diventa utente Keystone e cartella dei file esca
NOME_VALIDO = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
GRAVITA = {"success": "GRAVE", "failure": "ATTENZIONE",
           "ruolo_assegnato": "GRAVE", "gruppo_assegnato": "GRAVE",
           "esca_disattivata": "ATTENZIONE",
           "esca_eliminata": "ATTENZIONE",
           "brute_force": "GRAVE", "ricognizione": "GRAVE",
           "quarantena": "GRAVE"}
LOG = config.logging.getLogger(__name__)


def token_valido(token):
    """Verifica su Keystone un token e che abbia il ruolo admin."""
    return cloud.Cloud().token_admin(token)


def richiede_token(funzione):
    @functools.wraps(funzione)
    def controllo(*args, **kwargs):
        if token_valido(request.headers.get("X-Auth-Token")):
            return funzione(*args, **kwargs)
        return errore(401, "Token Keystone mancante, non valido o senza "
                           "ruolo admin")
    return controllo


def errore(codice, messaggio):
    return jsonify(error=messaggio), codice


def esca_attiva(nome):
    return next((h for h in db.list_honeytokens() if h["name"] == nome),
                None)


@app.route("/")
def versioni():
    """Descrizione del servizio, senza autenticazione."""
    return jsonify(service="honey-stack", versions=["v1"])


@app.route("/api/v1/alerts")
@richiede_token
def api_alerts():
    luoghi = {h["name"]: h["luogo"]
              for h in db.list_honeytokens(only_active=False)}
    return jsonify([dict(a, gravita=GRAVITA.get(a["outcome"], ""),
                         luogo=luoghi.get(a["name"], ""))
                    for a in db.list_alerts(100)])


@app.route("/api/v1/honeytokens")
@richiede_token
def api_honeytokens():
    return jsonify([dict(h) for h in db.list_honeytokens()])


@app.route("/api/v1/honeytokens", methods=["POST"])
@richiede_token
def api_crea_honeytoken():
    dati = request.get_json(silent=True) or {}
    nome = str(dati.get("name", "")).strip()
    luogo = str(dati.get("location", "")).strip()
    if not NOME_VALIDO.match(nome) or nome.startswith("."):
        return errore(400, "Nome dell'esca mancante o non valido: lettere, "
                           "cifre, _ . - (massimo 64)")
    try:
        manager.create_honeytoken(nome, luogo)
    except ValueError as e:
        return errore(409, str(e))
    LOG.info("Honeytoken creato dalle API: %s", nome)
    return jsonify(dict(esca_attiva(nome))), 201


@app.route("/api/v1/honeytokens/<nome>", methods=["DELETE"])
@richiede_token
def api_elimina_honeytoken(nome):
    try:
        manager.delete_honeytoken(nome)
    except ValueError as e:
        return errore(404, str(e))
    LOG.info("Honeytoken eliminato dalle API: %s", nome)
    return "", 204


@app.route("/api/v1/honeytokens/<nome>/files/<file>")
@richiede_token
def api_file_esca(nome, file):
    if file not in FILE_ESCA or esca_attiva(nome) is None:
        abort(404)
    percorso = os.path.join(manager.DECOY_DIR, nome, file)
    if not os.path.exists(percorso):
        abort(404)
    return send_file(percorso, mimetype="text/plain", as_attachment=True,
                     download_name=file)


@app.route("/api/v1/quarantines")
@richiede_token
def api_quarantines():
    return jsonify([dict(q) for q in db.list_quarantine()])


@app.route("/api/v1/quarantines/<int:voce>/release", methods=["POST"])
@richiede_token
def api_rilascia(voce):
    attiva = next((q for q in db.list_quarantine() if q["id"] == voce), None)
    if attiva is None:
        return errore(404, "Nessuna quarantena attiva con id %d" % voce)
    return jsonify(server_name=quarantena.rilascia_voce(attiva))


def main():
    """Punto di ingresso del comando honey-stack-dashboard."""
    config.setup_log()
    config.attendi(AUTH_URL, "Keystone")
    LOG.info("API di Honey-Stack sulla porta %s", PORTA)
    app.run(host="0.0.0.0", port=PORTA)


if __name__ == "__main__":
    main()
