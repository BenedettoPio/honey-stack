"""Honey-Stack - Dashboard e API.

Interfaccia web e API REST per creare gli honeytoken, scaricare i file
esca e consultare gli allarmi. L'accesso richiede un utente Keystone
con ruolo admin.
Avvio (dopo source openrc admin admin): python -m honeystack.app
"""
import functools
import os

import openstack
from flask import (Flask, abort, jsonify, redirect, render_template_string,
                   request, send_file, session, url_for)

from honeystack import db, manager

app = Flask(__name__)
app.secret_key = os.urandom(32)

AUTH_URL = os.environ.get("OS_AUTH_URL", "http://127.0.0.1/identity")
PORTA = int(os.environ.get("HONEYSTACK_PORT", "5050"))
GRAVITA = {"success": "GRAVE", "failure": "ATTENZIONE"}

STILE = """
body { font-family: sans-serif; margin: 2em; background: #f6f6f6; }
h1 { margin-bottom: 0; } table { border-collapse: collapse; width: 100%;
background: white; margin-bottom: 2em; } th, td { padding: 6px 10px;
border-bottom: 1px solid #ddd; text-align: left; } th { background: #eee; }
.grave { color: white; background: #c0392b; padding: 2px 8px; }
.attenzione { color: black; background: #f1c40f; padding: 2px 8px; }
.msg { background: #dff0d8; padding: 8px; } .err { color: #c0392b; }
"""

PAGINA_LOGIN = """<!doctype html><html><head><meta charset="utf-8">
<title>Honey-Stack - Login</title><style>{{ stile }}</style></head><body>
<h1>Honey-Stack</h1><p>Accesso con credenziali OpenStack (ruolo admin)</p>
{% if errore %}<p class="err">{{ errore }}</p>{% endif %}
<form method="post">
<p><input name="utente" placeholder="Utente"></p>
<p><input name="password" type="password" placeholder="Password"></p>
<p><button>Accedi</button></p></form></body></html>"""

PAGINA_DASHBOARD = """<!doctype html><html><head><meta charset="utf-8">
<script>setTimeout(function () { location.replace("/"); }, 10000);</script>
<title>Honey-Stack</title><style>{{ stile }}</style></head><body>
<h1>Honey-Stack</h1>
<p>Utente: <b>{{ utente }}</b> - <a href="{{ url_for('logout') }}">Esci</a></p>
{% if messaggio %}<p class="msg">{{ messaggio }}</p>{% endif %}
<h2>Allarmi ({{ allarmi|length }})</h2>
<table><tr><th>Gravita'</th><th>Orario (UTC)</th><th>Honeytoken</th>
<th>Luogo dell'esca</th><th>IP sorgente</th><th>Strumento</th></tr>
{% for a in allarmi %}<tr>
<td><span class="{{ 'grave' if a.outcome == 'success' else 'attenzione' }}">
{{ gravita.get(a.outcome, a.outcome) }}</span></td>
<td>{{ a.event_time[:19] }}</td><td>{{ a.name }}</td>
<td>{{ luoghi.get(a.name, '') }}</td><td>{{ a.source_ip }}</td>
<td>{{ a.agent }}</td></tr>{% endfor %}</table>
<h2>Honeytoken attivi ({{ esche|length }})</h2>
<table><tr><th>Nome</th><th>Luogo</th><th>Creato</th><th>File esca</th>
<th></th></tr>
{% for h in esche %}<tr><td>{{ h.name }}</td><td>{{ h.luogo }}</td>
<td>{{ h.created_at[:19] }}</td>
<td><a href="{{ url_for('scarica', nome=h.name, file='clouds.yaml') }}">clouds.yaml</a>
<a href="{{ url_for('scarica', nome=h.name, file='openrc') }}">openrc</a></td>
<td><form method="post" action="{{ url_for('elimina', nome=h.name) }}">
<button>Elimina</button></form></td></tr>{% endfor %}</table>
<h2>Nuovo honeytoken</h2>
<form method="post" action="{{ url_for('crea') }}">
<input name="nome" placeholder="Nome (es. backup_admin)">
<input name="luogo" placeholder="Luogo dell'esca">
<button>Crea</button></form></body></html>"""


def login_keystone(utente, password):
    """Autentica l'utente su Keystone e verifica il ruolo admin."""
    try:
        conn = openstack.connect(
            auth_url=AUTH_URL, username=utente, password=password,
            project_name="admin", user_domain_name="Default",
            project_domain_name="Default",
            load_yaml_config=False, load_envvars=False)
        accesso = conn.session.auth.get_access(conn.session)
    except Exception:
        return False
    return "admin" in accesso.role_names


def token_valido(token):
    """Verifica un token Keystone e che abbia il ruolo admin."""
    if not token:
        return False
    try:
        conn = openstack.connect()
        risposta = conn.session.get(
            AUTH_URL + "/v3/auth/tokens",
            headers={"X-Subject-Token": token}, raise_exc=False)
    except Exception:
        return False
    if risposta.status_code != 200:
        return False
    ruoli = risposta.json()["token"].get("roles", [])
    return any(r["name"] == "admin" for r in ruoli)


def richiede_login(funzione):
    @functools.wraps(funzione)
    def controllo(*args, **kwargs):
        if "utente" not in session:
            return redirect(url_for("login"))
        return funzione(*args, **kwargs)
    return controllo


def richiede_token(funzione):
    @functools.wraps(funzione)
    def controllo(*args, **kwargs):
        if "utente" in session or token_valido(
                request.headers.get("X-Auth-Token")):
            return funzione(*args, **kwargs)
        return jsonify(error="Token Keystone mancante o non valido"), 401
    return controllo


@app.route("/login", methods=["GET", "POST"])
def login():
    errore = None
    if request.method == "POST":
        utente = request.form.get("utente", "")
        if login_keystone(utente, request.form.get("password", "")):
            session["utente"] = utente
            return redirect(url_for("dashboard"))
        errore = "Credenziali non valide o utente senza ruolo admin"
    return render_template_string(PAGINA_LOGIN, stile=STILE, errore=errore)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@richiede_login
def dashboard():
    luoghi = {h["name"]: h["luogo"]
              for h in db.list_honeytokens(only_active=False)}
    return render_template_string(
        PAGINA_DASHBOARD, stile=STILE, utente=session["utente"],
        allarmi=db.list_alerts(100), esche=db.list_honeytokens(),
        luoghi=luoghi, gravita=GRAVITA, messaggio=request.args.get("msg"))


@app.route("/honeytokens", methods=["POST"])
@richiede_login
def crea():
    nome = request.form.get("nome", "").strip()
    luogo = request.form.get("luogo", "").strip()
    if not nome:
        messaggio = "Inserisci un nome"
    else:
        try:
            manager.create_honeytoken(nome, luogo)
            messaggio = "Honeytoken creato: " + nome
        except ValueError as errore:
            messaggio = str(errore)
    return redirect(url_for("dashboard", msg=messaggio))


@app.route("/honeytokens/<nome>/delete", methods=["POST"])
@richiede_login
def elimina(nome):
    try:
        manager.delete_honeytoken(nome)
        messaggio = "Honeytoken eliminato: " + nome
    except ValueError as errore:
        messaggio = str(errore)
    return redirect(url_for("dashboard", msg=messaggio))


@app.route("/honeytokens/<nome>/<file>")
@richiede_login
def scarica(nome, file):
    if file not in ("clouds.yaml", "openrc"):
        abort(404)
    if not any(h["name"] == nome for h in db.list_honeytokens()):
        abort(404)
    percorso = os.path.join(manager.DECOY_DIR, nome, file)
    if not os.path.exists(percorso):
        abort(404)
    return send_file(percorso, as_attachment=True, download_name=file)


@app.route("/api/v1/honeytokens")
@richiede_token
def api_honeytokens():
    return jsonify([dict(h) for h in db.list_honeytokens()])


@app.route("/api/v1/alerts")
@richiede_token
def api_alerts():
    return jsonify([dict(a, gravita=GRAVITA.get(a["outcome"], ""))
                    for a in db.list_alerts(100)])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORTA)
